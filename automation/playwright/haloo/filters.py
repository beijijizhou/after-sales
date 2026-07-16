import re

from automation.playwright.haloo.date_picker import set_production_date_filter


MAX_SAFE_EXPORT_ROWS = 50_000


def apply_production_item_filter(page, start_date, end_date, report):
    report("3/7 正在展开高级搜索")
    _open_advanced_search(page)
    report(f"正在设置生产时间：{start_date} 至 {end_date}")
    set_production_date_filter(page, start_date, end_date)
    report("4/7 正在查询生产项（仅查询一次）")
    click_named_button(page, ["查询", "搜索"])
    _wait_for_results(page)
    item_count = _read_result_count(page)
    if item_count is None:
        raise RuntimeError("安全停止：无法确认生产项数量，未点击最终导出")
    report(f"5/7 查询完成：{item_count:,} 条生产项")
    if item_count > MAX_SAFE_EXPORT_ROWS:
        raise RuntimeError(
            f"安全停止：当前有 {item_count:,} 条，日期筛选未正确传递，"
            "未点击最终导出"
        )
    return item_count


def click_named_button(page, names):
    normalized_names = {_normalize_text(name) for name in names}
    for frame in page.frames:
        buttons = frame.locator("button")
        for index in range(buttons.count()):
            button = buttons.nth(index)
            if not button.is_visible() or not button.is_enabled():
                continue
            if _normalize_text(button.inner_text()) in normalized_names:
                button.click()
                return
    raise RuntimeError(f"没有找到按钮：{' / '.join(names)}")


def _open_advanced_search(page):
    if _has_visible_text(page, "生产时间"):
        return
    click_named_button(page, ["高级搜索"])
    page.wait_for_timeout(500)


def _has_visible_text(page, text):
    for frame in page.frames:
        matches = frame.get_by_text(text, exact=True)
        for index in range(matches.count()):
            if matches.nth(index).is_visible():
                return True
    return False


def _wait_for_results(page):
    loading_was_visible = False
    for _ in range(20):
        if _has_loading_indicator(page):
            loading_was_visible = True
            break
        page.wait_for_timeout(250)
    if loading_was_visible:
        for _ in range(120):
            if not _has_loading_indicator(page):
                return
            page.wait_for_timeout(250)
        raise RuntimeError("查询已发出，但生产项加载超过30秒")
    page.wait_for_timeout(1500)


def _has_loading_indicator(page):
    for frame in page.frames:
        loading = frame.locator(".ant-spin-spinning, .el-loading-mask")
        for index in range(loading.count()):
            if loading.nth(index).is_visible():
                return True
    return False


def _read_result_count(page):
    counts = []
    pattern = re.compile(r"共\s*([\d,]+)\s*条")
    for frame in page.frames:
        for text in frame.locator("body").all_inner_texts():
            counts.extend(
                int(value.replace(",", ""))
                for value in pattern.findall(text)
            )
    return max(counts) if counts else None


def _normalize_text(value):
    return re.sub(r"\s+", "", str(value or ""))
