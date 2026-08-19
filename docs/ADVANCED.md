# Advanced: ANN caches that refuse to eat the archive

This guide is for people who already ran [`START_HERE.md`](../START_HERE.md)
and want the design that keeps showing up in production: **why a vector
index clobber looks like a model failure**, how sqlite-vec / FAISS /
turbovec / Chroma persist, and how this kernel differs from those
libraries.

Search terms this document is meant to answer: *vector index wiped dual
write*, *RAG empty after deploy SQL still has rows*, *sqlite-vec plus
ANN*, *turbovec 4-bit save clobber*, *present_ids allowlist turbovec*,
*fail-open ANN fail-closed auth*.

---

## 1. The failure that looks like a dumb model

A dual-write process loads an empty in-memory `IdMapIndex` (new file,
failed load, or a worker that never called `add` after a restart) and
`save()`s over a multi-hundred-MB backfill. Recall dies. SQL still has
every row. You debug the LLM.

That path has three hidden properties:

1. **The save succeeded.** Atomic replace of a tiny snapshot is a
   successful write in FAISS `write_index` and turbovec `write()` /
   `atomic_save`.
2. **The archive is fine.** sqlite-vec `vec0` (or a regular blob
   column) still answers brute-force KNN. You will not notice if the
   query path only reads the ANN.
3. **Fail-open and fail-closed get copied onto the wrong layer.** People
   copy “fail-open RAG” and accidentally fail-open **sudo**. This kernel
   fail-opens only the **accelerator**. Identity, allowlists, and review
   envelopes stay fail-closed.

Per the Cynical0n3 NotebookLM (`systems`): the transformed
representation must never redefine the source; replicating fields across
systems instead of a normalized store leads to side-effect-heavy
triggers. Fail-closed is the required default for mutations that would
corrupt state. Fail-open is only permissible for non-authoritative
secondary similarity scans.

The correct primitive is **SQL-first + shrink-guard save**, not “the
ANN is memory.”

---

## 2. Quantified incident (lab shape, no live host)

Overnight backfill wrote ~**300,000** vectors into SQL and a ~**300 MB**
`.tvim`. A daytime dual-write worker started with an empty in-memory
index (no load, or load of a missing file) and called `save()`.

| Step | Without this kernel | With this kernel |
| ---- | ------------------- | ---------------- |
| Backfill | ~300k rows in SQL + ~300 MB `.tvim` | Same |
| Worker start | Empty `IdMapIndex` in RAM | Same |
| `add` of 1 new chunk | RAM holds 1 vector | Same |
| `save()` | Atomic replace → ~KB file | **RuntimeError**; previous ~300 MB kept |
| Query path (ANN only) | RAG empty; you debug the model | Cache still hot, or SQL fallback |
| Restore | Re-embed from scratch if SQL was also treated as cache | Delete `.tvim` only if needed; backfill from SQL |

A/B on a lab codebase-search gate (ANN vs sqlite-vec, same queries):
agreement@10 stayed in the **0.9** band when the cache was intact.
After a clobber, agreement collapses to “no hits” while SQL still
matches. Track **silent size drops** (should be **zero**) vs loud
`cynicvec save blocked` (should be rare).

---

## 3. `present_ids` before `search(allowlist=)`

turbovec `search(allowlist=)` raises if you name an id the index does
not hold. Metadata-only rows are normal after partial backfill (SQL
commit succeeded; ANN add skipped or crashed). Intersect first:

```python
eligible = sql_candidate_rowids(...)
present = ann.present_ids(eligible)
hits = ann.search(query, k=10, allowlist=present) if present else []
```

Empty `present` is a healthy miss → SQL/KNN, not an exception storm.

---

## 4. Capacity

ANN search competes with inference VRAM on small GPUs. Pair with
`edge-capacity-gate`. Prefer SQL when under pressure. The shrink guard
does not free VRAM; it only refuses to eat the archive.

---

## How this stands out

Researched with Context7 (`libraryId=/asg017/sqlite-vec` `vec0` virtual
table + brute-force `vec_distance_L2` on regular tables;
`libraryId=/facebookresearch/faiss` `write_index` / `read_index` in
`faiss/index_io.h` — **no size check**;
`libraryId=/chroma-core/chroma` `PersistentClient(path=...)` writes
`chroma.sqlite3` instantly, `.persist()` removed in 0.4.0, `.reset()`
disabled by default) and GitHub-MCP (`asg017/sqlite-vec` file
`site/features/knn.md`; `facebookresearch/faiss` file `faiss/index_io.h`;
`RyanCodrai/turbovec` files `turbovec-python/python/turbovec/_persist.py`
`atomic_save`, `turbovec-python/src/lib.rs` `write`; `chroma-core/chroma`
file `docs/mintlify/docs/overview/migration.mdx`). DeepWiki on
`RyanCodrai/turbovec` describes `write(path)` serializing the
in-memory packed codes to `.tv` / `.tvim` as-is — caches are not stored,
and **byte-size of the previous file is not a persist invariant**.
GitHub `search_code` for `"would shrink"` in `repo:RyanCodrai/turbovec`
returned **zero** hits. `cynicvec in:name` returned **zero** CynicalTyr
repos. Sibling kernels `epistemic-deny`, `sidecar-occupancy`,
`gated-rewoo`, and `agent-review-envelope` are denies, occupancy, planner
gates, and speech queues — not ANN persist.

| Obvious alternative | What they optimize | What they miss | This kernel |
| ------------------- | ------------------ | -------------- | ----------- |
| sqlite-vec `vec0` (`site/features/knn.md`) | Vectors *in* SQLite; JOIN back to source tables; manual `vec_distance_*` KNN | No separate 4-bit ANN cache; no shrink fuse because SQL *is* the store | ANN cache **beside** sqlite-vec; SQL remains restore |
| FAISS `write_index` (`faiss/index_io.h`) | Fast serialize of whatever `Index*` is in RAM | Overwrites `fname` with no prev-size vs new-size guard. Wiki: does not validate loaded files | `save()` aborts if a `>50 MB` file would shrink `>50%` |
| turbovec `atomic_save` (`_persist.py`) | Atomic temp + `os.replace`; sidecar handle bijection; durable fsync | Handle/sidecar consistency, **not** “do not replace 300 MB with 4 KB” | Same atomic replace **plus** shrink guard; ids *are* SQL rowids (no payload sidecar) |
| Chroma `PersistentClient` (`chromadb/__init__.py`) | Instant disk writes; `chroma.sqlite3` in `persist_directory` | The persist dir **is** the database. `.reset()` is gated; a dual-write to a *second* ANN file is out of scope | This kernel is the second file, and it must not redefine SQL |
| `epistemic-deny` (sibling) | Deny-as-packet | Missing ANN is not a permission deny | Fail-open accelerator; fail-closed identity |
| `agent-review-envelope` (sibling) | Generator ≠ evaluator for *speech* | Queues do not restore a clobbered `.tvim` | Keep SQL; file a sitrep later |

**Non-obvious / high-leverage:** atomic persist is not a shrink guard.
turbovec already paid for crash-safe replace and sidecar bijection
(issue notes in `_persist.py`). The 3am bug is a **successful** atomic
write of the wrong snapshot. The fuse is two constants: `50_000_000`
bytes and `0.5`. `present_ids` is the other fuse: turbovec allowlists
are closed over index membership, not over SQL eligibility.

**Mental model to replace:** adopters think the vector index is memory
(Chroma persist, FAISS file, turbovec `.tvim`). The governing model is
**SQL is the archive; ANN is a cache.** Per Cynical0n3 NotebookLM
(`systems`): fail-open only the secondary scan; abort mutations that
would let the transformed copy redefine the source.

**Incentive:** the stack will keep querying only the ANN because it is
faster (~tens of ms vs seconds of sqlite-vec on large tables) and
because one query path is cheaper than two. After a clobber, that path
returns empty and the dashboard says “model quality dropped.”

**Second-order effect:** once copied, teams optimize ANN hit-rate and
add `save(force=True)` or an MCP `load_tvim_from_url` so a demo never
waits on backfill. That metric is the next clobber. Count silent size
drops (zero) vs SQL-fallback rate when turbovec is missing (healthy).
Do **not** copy fail-open onto auth.

---

## 5. Measuring use

| Signal | Healthy |
| ------ | ------- |
| `RuntimeError` from construct (no turbovec) | Caller used SQL |
| `RuntimeError` from `save` (shrink) | Rare, loud; previous file kept |
| Silent `.tvim` size drop `>50%` on a `>50 MB` file | **Zero** |
| `search(allowlist=)` exceptions | Zero after `present_ids` |

---

## 6. Short comparison (same facts, operator table)

See **How this stands out** above for library/file evidence. In one
line: this is not a vector database. It is a kernel you drop into the
dual-write you already have. You still own SQL, backfill, and the query
tool. sqlite-vec remains how you restore.
