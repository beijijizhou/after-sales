import unittest

from automation.playwright.s2b.page_actions import click_visible_text
from utils.google_sheets import values_for_range


class GoogleSheetsRangeTests(unittest.TestCase):
    def test_prefers_exact_requested_range(self):
        requested = "'0808'!A1:K1200"
        values = [["exact"]]

        self.assertIs(
            values_for_range({requested: values}, "0808", requested),
            values,
        )

    def test_accepts_normalized_returned_range(self):
        requested = "'0808'!A1:K1200"
        values = [["normalized"]]

        self.assertIs(
            values_for_range({"0808!A1:K1200": values}, "0808", requested),
            values,
        )

    def test_does_not_return_another_sheet(self):
        requested = "'0808'!A1:K1200"

        self.assertEqual(
            values_for_range({"0807!A1:K1200": [["wrong"]]}, "0808", requested),
            [],
        )


class _Candidate:
    def __init__(self, visible):
        self.visible = visible
        self.clicked = False

    def is_visible(self):
        return self.visible

    def click(self):
        self.clicked = True


class _Matches:
    def __init__(self, candidates):
        self.candidates = candidates

    def count(self):
        return len(self.candidates)

    def nth(self, index):
        return self.candidates[index]


class _Page:
    def __init__(self, candidates):
        self.matches = _Matches(candidates)
        self.request = None

    def get_by_text(self, label, exact):
        self.request = (label, exact)
        return self.matches


class S2BPageActionTests(unittest.TestCase):
    def test_clicks_first_visible_exact_text_match(self):
        hidden = _Candidate(False)
        visible = _Candidate(True)
        page = _Page([hidden, visible])

        click_visible_text(page, "搜索")

        self.assertEqual(page.request, ("搜索", True))
        self.assertFalse(hidden.clicked)
        self.assertTrue(visible.clicked)

    def test_missing_visible_match_raises_clear_error(self):
        page = _Page([_Candidate(False)])

        with self.assertRaisesRegex(RuntimeError, "S2B 没有找到按钮：搜索"):
            click_visible_text(page, "搜索")


if __name__ == "__main__":
    unittest.main()
