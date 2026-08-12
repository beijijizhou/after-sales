"""Reusable S2B page interactions."""


def click_visible_text(page, label):
    """Click the first visible exact-text match or fail clearly."""
    matches = page.get_by_text(label, exact=True)
    for index in range(matches.count()):
        candidate = matches.nth(index)
        if candidate.is_visible():
            candidate.click()
            return
    raise RuntimeError(f"S2B 没有找到按钮：{label}")
