import re


def set_production_date_filter(page, start_date, end_date):
    selected, frame, calendar = _open_production_calendar(page)
    _click_calendar_date(calendar, start_date)
    _click_calendar_date(calendar, end_date)
    _confirm_calendar(frame, calendar)
    page.wait_for_timeout(500)
    actual_values = [field.input_value() for field, _ in selected]
    expected_dates = [start_date.isoformat(), end_date.isoformat()]
    if any(
        expected not in actual
        for expected, actual in zip(expected_dates, actual_values)
    ):
        raise RuntimeError("生产时间未成功写入，已停止查询和导出")


def _open_production_calendar(page):
    for _ in range(60):
        pairs = _find_date_input_pairs(page)
        if pairs:
            break
        page.wait_for_timeout(500)
    else:
        raise RuntimeError("生产项页面加载30秒后仍未找到生产时间输入框")

    opened = _find_visible_calendar(page)
    if opened is not None:
        return pairs[0], *opened
    for selected in pairs:
        picker = selected[0][0].locator(
            "xpath=ancestor::span[contains(@class,'ant-calendar-picker')][1]"
        )
        picker.dispatch_event("mousedown")
        picker.dispatch_event("click")
        page.wait_for_timeout(300)
        opened = _find_visible_calendar(page)
        if opened is not None:
            return selected, *opened
    raise RuntimeError("找到生产时间，但点击后没有出现日历")


def _find_visible_calendar(page):
    for frame in page.frames:
        calendars = frame.locator(".ant-calendar-picker-container")
        for index in range(calendars.count()):
            calendar = calendars.nth(index)
            if calendar.is_visible():
                return frame, calendar
    return None


def _click_calendar_date(calendar, target_date):
    title = f"{target_date.year}年{target_date.month}月{target_date.day}日"
    for _ in range(120):
        target = calendar.locator(f'td[title="{title}"]')
        for index in range(target.count()):
            cell = target.nth(index)
            classes = cell.get_attribute("class") or ""
            if cell.is_visible() and "disabled" not in classes:
                cell.click(force=True)
                return
        direction = _calendar_direction(calendar, target_date)
        selector = (
            ".ant-calendar-prev-month-btn"
            if direction < 0
            else ".ant-calendar-next-month-btn"
        )
        if not _click_visible(calendar.locator(selector)):
            break
    raise RuntimeError(f"日历中无法选择日期：{target_date}")


def _calendar_direction(calendar, target_date):
    titles = calendar.locator(
        "td.ant-calendar-cell:not(.ant-calendar-last-month-cell)"
        ":not(.ant-calendar-next-month-btn-day)"
    ).evaluate_all("cells => cells.map(cell => cell.getAttribute('title'))")
    visible_months = [
        (int(match.group(1)), int(match.group(2)))
        for title in titles
        if (match := re.match(r"^(\d+)年(\d+)月", title or ""))
    ]
    if not visible_months:
        raise RuntimeError("无法识别当前日历月份")
    target_month = (target_date.year, target_date.month)
    return -1 if target_month < min(visible_months) else 1


def _confirm_calendar(frame, calendar):
    if _click_visible(calendar.get_by_text("确定", exact=True)):
        return
    if _click_visible(frame.locator(".ant-calendar-ok-btn")):
        return
    raise RuntimeError("日期范围已选择，但没有找到日历确定按钮")


def _click_visible(locator):
    for index in range(locator.count()):
        candidate = locator.nth(index)
        if candidate.is_visible():
            candidate.click(force=True)
            return True
    return False


def _find_date_input_pairs(page):
    pairs = []
    for frame in page.frames:
        labels = frame.get_by_text("生产时间", exact=True)
        for index in range(labels.count()):
            label = labels.nth(index)
            if not label.is_visible():
                continue
            row = label.locator(
                "xpath=ancestor::*[contains(@class,'ant-form-item-row')][1]"
            )
            start = row.locator('input[placeholder="开始日期"]')
            end = row.locator('input[placeholder="结束日期"]')
            if start.count() and end.count():
                pairs.append([
                    (start.first, "开始日期"),
                    (end.first, "结束日期"),
                ])
    return pairs
