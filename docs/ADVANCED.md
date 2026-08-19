# Advanced: ANN caches that refuse to eat the archive

Search terms: *sqlite-vec plus ANN*, *turbovec 4-bit*, *vector index
clobbered dual write*, *RAG empty after deploy*, *present_ids allowlist
turbovec*.

---

## 1. Fail-open vs fail-closed

People copy “fail-open RAG” and accidentally fail-open **sudo**. CynicVec
fail-opens only the **accelerator**. Identity, allowlists, and review
envelopes stay fail-closed.

---

## 2. The 3am bug

A dual-write process loads an empty in-memory index and `save()`s over a
multi-hundred-MB backfill. Recall dies; SQL still has rows; you debug the
model. The shrink guard (`>50MB` and new file `<50%`) is the cheap fuse.

---

## 3. `present_ids`

`search(allowlist=)` throws if you name an id the index does not hold.
Metadata-only rows are normal after partial backfill. Intersect first.

---

## 4. Capacity

ANN search competes with inference VRAM on small GPUs. Pair with
`edge-capacity-gate`. Prefer SQL when under pressure.

---

## 5. Comparison

| Design | Restore after bad write |
| ------ | ----------------------- |
| ANN authoritative | Often no |
| SQL + ANN cache (this) | Yes — delete `.tvim`, backfill |

---

## 6. Measuring use

Track `RuntimeError` from `save` (should be rare and loud) vs silent size
drops (should be zero).

## Hidden dynamics (short)

- Pattern: ANN is a cache. SQL (or sqlite-vec) stays source of truth. Fail-open on the accelerator only.
- Loop: Empty in-memory index + save() over a huge .tvim → RAG dies at 3am while SQL still has rows.
- Incentive: Making ANN authoritative “simplifies” the stack until the first bad write. Then there is no restore.
- Leverage: save() refuse if new file < 50% of a >50MB index. present_ids before search(allowlist=).
- Harness: Do not expose raw index load. Optional: “is cache present?” Your memory_query tool stays in the daemon.
- Custom AI: Embed → SQL row → add → save. Query: SQL candidates → present_ids → search(allowlist=). Catch RuntimeError.

