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
        with self.assertRaises(RuntimeError):
            CynicVec("/tmp/demo.tvim", dim=8)


if __name__ == "__main__":
    unittest.main()
