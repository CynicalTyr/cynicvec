from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cynicvec import CynicVec, _HAS_TURBOVEC


class CynicvecTests(unittest.TestCase):
    def test_missing_turbovec_raises(self) -> None:
        if _HAS_TURBOVEC:
            self.skipTest("turbovec installed")
        with self.assertRaises(RuntimeError) as ctx:
            CynicVec("/tmp/demo.tvim", dim=8)
        self.assertIn("SQL", str(ctx.exception))

    def test_save_source_has_shrink_guard(self) -> None:
        src = Path(__file__).resolve().parents[1] / "cynicvec.py"
        text = src.read_text(encoding="utf-8")
        self.assertIn("50_000_000", text)
        self.assertIn("0.5", text)
        self.assertIn("would shrink index", text)

    def test_present_ids_documented_for_allowlist(self) -> None:
        self.assertTrue(callable(getattr(CynicVec, "present_ids", None)))
        self.assertIn("allowlist", (CynicVec.present_ids.__doc__ or "").lower())


if __name__ == "__main__":
    unittest.main()
