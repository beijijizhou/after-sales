from datetime import date
import unittest

from ui.production_data.controls import resolve_production_period


class ProductionDataControlTests(unittest.TestCase):
    def test_single_date_is_a_complete_same_day_range(self):
        selected = date(2026, 8, 6)
        self.assertEqual(
            resolve_production_period("当天", selected),
            (selected, selected),
        )

    def test_quick_range_is_derived_from_selected_end_date(self):
        self.assertEqual(
            resolve_production_period("近7日", date(2026, 8, 6)),
            (date(2026, 7, 31), date(2026, 8, 6)),
        )


if __name__ == "__main__":
    unittest.main()
