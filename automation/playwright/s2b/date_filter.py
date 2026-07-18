def apply_production_time_filter(page, start_date, end_date, report):
    report(f"正在设置生产时间：{start_date} 至 {end_date}")
    row = page.locator(".orderSearchList.arriveTime")
    if not row.count():
        raise RuntimeError("没有找到 S2B 生产时间筛选项")
    start = row.locator('input[placeholder="开始时间"]')
    end = row.locator('input[placeholder="结束时间"]')
    _set_datetime(page, start, f"{start_date:%Y-%m-%d} 00:00:00")
    _set_datetime(page, end, f"{end_date:%Y-%m-%d} 23:59:59")
    values = [start.input_value(), end.input_value()]
    expected = [start_date.isoformat(), end_date.isoformat()]
    if any(date not in value for date, value in zip(expected, values)):
        raise RuntimeError("S2B 生产时间未成功写入，已停止查询")

    report("正在点击 S2B 搜索")
    _click_text(page, "搜索")
    _wait_for_loading(page)


def _set_datetime(page, field, value):
    _close_open_calendar(page)
    field.click(force=True)
    calendar = _wait_for_calendar(page)
    editor = calendar.locator("input.ant-calendar-input")
    editor.click(force=True)
    editor.press("Meta+A")
    editor.press_sequentially(value, delay=10)
    confirm = calendar.locator(".ant-calendar-ok-btn")
    confirm.click(force=True)
    for _ in range(40):
        if field.input_value() == value:
            _close_open_calendar(page)
            return
        page.wait_for_timeout(250)
    raise RuntimeError(f"S2B 日期未成功确认：{value}")


def _wait_for_calendar(page):
    for _ in range(40):
        calendars = page.locator(".ant-calendar-picker-container")
        for index in reversed(range(calendars.count())):
            calendar = calendars.nth(index)
            if calendar.is_visible():
                return calendar
        page.wait_for_timeout(250)
    raise RuntimeError("S2B 日期选择器未打开")


def _close_open_calendar(page):
    calendars = page.locator(".ant-calendar-picker-container")
    if any(
        calendars.nth(index).is_visible()
        for index in range(calendars.count())
    ):
        page.get_by_text("财务结算中心", exact=True).click(force=True)
        page.wait_for_timeout(300)


def _click_text(page, text):
    matches = page.get_by_text(text, exact=True)
    for index in range(matches.count()):
        candidate = matches.nth(index)
        if candidate.is_visible():
            candidate.click()
            return
    raise RuntimeError(f"S2B 没有找到按钮：{text}")


def _wait_for_loading(page):
    page.wait_for_timeout(500)
    loading = page.locator(".ant-spin-spinning")
    for index in range(loading.count()):
        loading.nth(index).wait_for(state="hidden", timeout=30_000)
