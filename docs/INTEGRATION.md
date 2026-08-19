# Integration patterns

This kernel is the **ANN cache policy** beside a SQL (or sqlite-vec)
table. The table itself lives in *your* app. There is no MCP adapter in
this repo.

```
Your embed worker
    │
    ▼
SQL / sqlite-vec row     →  source of truth
    │
    ▼
CynicVec.add + save()    →  .tvim cache (shrink-guarded)

Your query worker
    │
    ▼
SQL candidates           →  present_ids  →  search(allowlist=)
    │
    └─ RuntimeError / empty present  →  SQL / brute-force KNN
```

Do **not** query only the `.tvim`. Do **not** add an MCP tool that loads
a `.tvim` from a URL.

## Map libraries onto this kernel

| Library (live docs) | Persist primitive | What you do instead |
| ------------------- | ----------------- | ------------------- |
| sqlite-vec (`libraryId=/asg017/sqlite-vec`, `site/features/knn.md`) | `vec0` virtual table **is** SQL | Keep it. This kernel is the optional 4-bit cache beside it. Manual `vec_distance_L2` is the fail-open path. |
| FAISS (`libraryId=/facebookresearch/faiss`, `faiss/index_io.h`) | `write_index(idx, fname)` overwrites | Do not call `write_index` from a dual-write worker without a size fuse. Prefer this wrapper’s `save()`. |
| turbovec (`RyanCodrai/turbovec`, `_persist.py` `atomic_save`) | Atomic `.tvim` + JSON sidecar | This kernel uses SQL rowids as ids (no payload sidecar) and adds the shrink guard `atomic_save` does not have. |
| Chroma (`libraryId=/chroma-core/chroma`, `PersistentClient`) | `persist_directory` / `chroma.sqlite3` **is** the DB | Do not treat Chroma persist as “the cache beside SQL.” If you dual-write Chroma *and* SQL, you still need a fuse; this kernel is the `.tvim` fuse. |

## Write order (do not invert)

**embed → SQL row → `CynicVec.add` → `save()`.**

If `add` or `save` fails, SQL still has the row. If you write the ANN
first and crash before SQL, you get an id the archive cannot explain.

```python
from pathlib import Path
from cynicvec import CynicVec

def get_ann(path: Path, dim: int) -> CynicVec | None:
    try:
        return CynicVec(path, dim=dim)
    except RuntimeError:
        return None  # caller uses SQL / sqlite-vec
```

On `save()` `RuntimeError` (shrink guard): keep the previous `.tvim`,
log to **stderr** (not stdout if this process is an MCP child), do not
`os.replace` yourself.

## Read order

**SQL candidates → `present_ids` → `search(allowlist=)`.**

turbovec `search(allowlist=)` throws if an id is absent from the index.
Metadata-only rows after partial backfill are normal.

```python
ann = get_ann(index_path, dim)
eligible = list(sql_candidate_rowids(query))
if ann is None:
    return sql_knn(query, eligible)
present = ann.present_ids(eligible)
if not present:
    return sql_knn(query, eligible)
return ann.search(query_vec, k=10, allowlist=present)
```

## Env names (names only)

Copy `.env.example` to `.env` in *your* worker. This library does not
read them. Typical names:

| Name | Role |
| ---- | ---- |
| `CYNICVEC_INDEX_PATH` | Path to the `.tvim` cache |
| `CYNICVEC_DIM` | Embedding width (example **2048**) |
| `MEMORY_VECTOR_BACKEND` / `SCARAB_VECTOR_BACKEND` | `cynicvec` vs `sqlite_vec` so you can skip the ANN |

Never commit `.env`. Never paste live values into issues.

## Harness (inspect only)

Keep `memory_query` / codebase-search in **your daemon**. Optional MCP
inspect: “does the cache file exist?” Do **not** ship
`load_tvim_from_url`. If you wrap anything in MCP, logs go to **stderr**
so stdout stays a JSON-RPC pipe. Use an **absolute** path. Restart the
harness after edits.

Paste-ready policy is in [`START_HERE.md`](../START_HERE.md) §5.

## Fail-open vs fail-closed

| Layer | Stance |
| ----- | ------ |
| Missing `turbovec` / missing `.tvim` | **Fail-open** → SQL/KNN |
| Shrink-guard `save` | **Fail-closed** on the *write* (keep previous file) |
| Auth, allowlist, identity | **Fail-closed** — do not copy ANN miss here |

## Pairing

- `edge-capacity-gate` — ANN vs inference VRAM.
- `epistemic-deny` — permission denies; not an ANN miss.
- `agent-review-envelope` — if a human must hear “we almost clobbered
  the index,” that is a sitrep, not a Slack from the saver process.
