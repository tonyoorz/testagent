import argparse
import unittest

import downloaderqgate as dq


class TestDownloaderQgateYear(unittest.TestCase):
    def test_year_overrides_default_defect_years_when_not_explicit(self):
        args = argparse.Namespace(year=2026, defect_years="2025,2026")
        updated = dq.apply_year_override(args, [])
        self.assertEqual(updated.defect_years, "2026")

    def test_explicit_defect_years_takes_precedence_over_year(self):
        args = argparse.Namespace(year=2026, defect_years="2024")
        updated = dq.apply_year_override(args, ["--defect-years", "2024"])
        self.assertEqual(updated.defect_years, "2024")


if __name__ == "__main__":
    unittest.main()
