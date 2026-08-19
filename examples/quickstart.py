#!/usr/bin/env python3
from pathlib import Path
from cynicvec import CynicVec, _HAS_TURBOVEC

print("turbovec installed:", _HAS_TURBOVEC)
if not _HAS_TURBOVEC:
    try:
        CynicVec("/tmp/demo.tvim", dim=8)
    except RuntimeError as exc:
        print("expected fail-open signal:", exc)
else:
    idx = CynicVec(Path("/tmp/cynicvec-demo.tvim"), dim=8)
    idx.add(1, [0.1] * 8)
    print(idx.search([0.1] * 8, k=1))
    idx.save()
