"""Unit tests for the two-stage face-swap matching helper.

Only the pure matching logic (``_optimal_pairs``) is exercised; the heavy
insightface / inswapper path is not, so these run without the optional face
dependencies. numpy is required (it ships with insightface in real runs).
"""

from __future__ import annotations

import itertools
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from generation.event_photo.face_swapper import _optimal_pairs  # noqa: E402


class OptimalPairsTest(unittest.TestCase):
    def test_beats_sequential_greedy_on_trap(self) -> None:
        # Row 0's top pick is col 0 (0.4). A sequential greedy assigns it there,
        # leaving row 1 with col 1 (0.2) -> total 0.6. The optimal assignment is
        # the cross (0,1)+(1,0) -> 0.9.
        sim = np.array([[0.4, 0.3], [0.6, 0.2]])
        pairs = sorted(_optimal_pairs(sim))
        self.assertEqual(pairs, [(0, 1), (1, 0)])
        self.assertAlmostEqual(sum(sim[r, c] for r, c in pairs), 0.9)

    def test_rectangular_uses_min_dimension_without_reuse(self) -> None:
        sim = np.array([[0.1, 0.9], [0.8, 0.2], [0.3, 0.3]])  # 3 rows, 2 cols
        pairs = _optimal_pairs(sim)
        self.assertEqual(len(pairs), 2)
        self.assertEqual(len({r for r, _ in pairs}), 2)  # no row reused
        self.assertEqual(len({c for _, c in pairs}), 2)  # no col reused

    def test_empty_or_degenerate_returns_empty(self) -> None:
        self.assertEqual(_optimal_pairs(np.empty((0, 0))), [])
        self.assertEqual(_optimal_pairs(np.empty((2, 0))), [])
        self.assertEqual(_optimal_pairs(np.empty((0, 3))), [])

    def test_assignment_is_globally_optimal(self) -> None:
        rng = np.random.default_rng(0)
        sim = rng.random((4, 4))
        got = sum(sim[r, c] for r, c in _optimal_pairs(sim))
        best = max(
            sum(sim[i, perm[i]] for i in range(4))
            for perm in itertools.permutations(range(4))
        )
        self.assertAlmostEqual(got, best)


if __name__ == "__main__":
    unittest.main()
