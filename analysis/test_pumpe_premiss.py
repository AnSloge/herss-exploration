"""Enhetstester for den reproduserbare pumpepremiss-analysen."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import pumpe_premiss as P  # noqa: E402


class PumpePremissTests(unittest.TestCase):
    def test_histogram_has_twenty_buckets_and_counts_everything(self):
        counts, edges = P.histogram(np.asarray([1.0, 2.0, 3.0, 4.0]))
        self.assertEqual(len(counts), 20)
        self.assertEqual(len(edges), 21)
        self.assertEqual(int(np.sum(counts)), 4)

    def test_forward_ratio_window_boundary(self):
        all_ratios, rising = P.forward_ratios(np.asarray([1.0, 2.0, 4.0, 8.0]), 2)
        self.assertCountEqual(all_ratios.tolist(), [2.0, 2.0, 2.0, 4.0, 4.0])
        self.assertEqual(len(rising), 5)

    def test_classification_thresholds_are_strict(self):
        self.assertEqual(P.classify_perfect_foresight(np.asarray([100.0, 119.0]), 1)["never"], 1)
        self.assertEqual(P.classify_perfect_foresight(np.asarray([100.0, 120.0]), 1)["conditional"], 1)
        self.assertEqual(P.classify_perfect_foresight(np.asarray([100.0, 133.0]), 1)["conditional"], 1)
        self.assertEqual(P.classify_perfect_foresight(np.asarray([100.0, 134.0]), 1)["always"], 1)

    def test_storage_units(self):
        self.assertEqual(P.storage_requirement_m3(1, 6), 21600.0)
        self.assertAlmostEqual(P.storage_requirement_m3(5, 24) / 1e6, 0.432)

    def test_pearson(self):
        self.assertAlmostEqual(P.pearson(np.asarray([1., 2., 3.]), np.asarray([2., 4., 6.])), 1.0)

    def test_hjelle_header_is_required(self):
        with self.assertRaisesRegex(AssertionError, "kolonneheader '0'"):
            # Intern logikk testes ved en minimal, midlertidig mangelfull fil.
            import tempfile
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "inflow.txt"
                path.write_text("Date_NodeID 3\n20220901 1.0\n", encoding="utf-8")
                P.read_hjelle_inflow(path, (P.dt.datetime(2022, 9, 1),))

    def test_secondary_has_leap_year_hour_count(self):
        secondary = P.read_secondary_no2(P.SECONDARY_XLSX)
        self.assertEqual(len(secondary.values), 8784)
        self.assertEqual(secondary.timestamps[0], P.dt.datetime(2023, 9, 1))
        self.assertEqual(secondary.timestamps[-1], P.dt.datetime(2024, 8, 31, 23))


if __name__ == "__main__":
    unittest.main()
