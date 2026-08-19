# Integration patterns

**Order of writes:** embed → SQL row → `CynicVec.add` → `save()`.
**Order of reads:** SQL candidates → `present_ids` → `search(allowlist=)`.

```python
from pathlib import Path
from cynicvec import CynicVec

def get_ann(path: Path, dim: int) -> CynicVec | None:
    try:
        return CynicVec(path, dim=dim)
    except RuntimeError:
        return None
```

On `save()` `RuntimeError` (shrink guard): keep the previous `.tvim`, log
to stderr, do not `os.replace` yourself.

Agent tool: `memory_query_readonly`. Never a tool that overwrites the
index from a URL.
