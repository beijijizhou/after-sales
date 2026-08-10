import unittest

from automation.playwright.chrome_session import find_erp_page


class _Page:
    def __init__(self, url):
        self.url = url
        self.closed = False
        self.goto_calls = []

    def is_closed(self):
        return self.closed

    def close(self):
        self.closed = True

    def goto(self, url, wait_until=None):
        self.goto_calls.append((url, wait_until))
        self.url = url


class _Context:
    def __init__(self, pages):
        self.pages = pages
        self.created = []

    def new_page(self):
        page = _Page("")
        self.pages.append(page)
        self.created.append(page)
        return page


class _Browser:
    def __init__(self, pages):
        self.contexts = [_Context(pages)]


class ChromeSessionTests(unittest.TestCase):
    def test_reuses_exact_page_and_closes_only_exact_duplicates(self):
        start_url = (
            "https://haloopod.merchant.hihumbird.com/factory/"
            "fnsz-sale/produceManage/produceItemsManage"
        )
        first = _Page(start_url)
        other = _Page(
            "https://haloopod.merchant.hihumbird.com/factory/export"
        )
        latest = _Page(start_url)
        browser = _Browser([first, other, latest])

        selected = find_erp_page(
            browser, "haloopod.merchant.hihumbird.com", "Haloo", start_url
        )

        self.assertIs(selected, latest)
        self.assertTrue(first.closed)
        self.assertFalse(other.closed)
        self.assertEqual(browser.contexts[0].created, [])

    def test_reuses_same_host_page_before_creating_a_new_tab(self):
        start_url = (
            "https://haloopod.merchant.hihumbird.com/factory/"
            "fnsz-sale/produceManage/produceItemsManage"
        )
        existing = _Page(
            "https://haloopod.merchant.hihumbird.com/factory/home"
        )
        browser = _Browser([existing])

        selected = find_erp_page(
            browser, "haloopod.merchant.hihumbird.com", "Haloo", start_url
        )

        self.assertIs(selected, existing)
        self.assertEqual(existing.goto_calls, [(start_url, "domcontentloaded")])
        self.assertEqual(browser.contexts[0].created, [])

    def test_creates_page_only_when_host_is_not_open(self):
        start_url = "https://overseasfactory.s2bdiy.com/factory/billDetails"
        browser = _Browser([_Page("https://example.com")])

        selected = find_erp_page(
            browser, "overseasfactory.s2bdiy.com", "S2B", start_url
        )

        self.assertIs(selected, browser.contexts[0].created[0])
        self.assertEqual(selected.goto_calls, [(start_url, "domcontentloaded")])


if __name__ == "__main__":
    unittest.main()
