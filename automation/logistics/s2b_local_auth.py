from pathlib import Path


S2B_ORDER_URL = "https://overseasfactory.s2bdiy.com/factory/orderManage"
S2B_ORDER_API_SUFFIX = "/orderProductOrder/getOrderList"
CHROME_PATH = Path(
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)


class S2BLocalLoginRequired(RuntimeError):
    pass


def local_login_available():
    return CHROME_PATH.is_file()


def refresh_local_s2b_token(account_name):
    if not local_login_available():
        raise S2BLocalLoginRequired(
            "当前部署环境不能打开本机S2B登录；请使用本地连接器"
        )

    from playwright.sync_api import sync_playwright

    from automation.playwright.chrome_session import connect_debug_chrome

    captured = {}
    with sync_playwright() as playwright:
        browser = connect_debug_chrome(playwright, S2B_ORDER_URL)
        page = _find_s2b_page(browser)
        if "/login" in page.url:
            raise S2BLocalLoginRequired(
                f"已打开S2B专用Chrome；请登录{account_name}账号并完成滑块，"
                "然后再次点击同步"
            )

        def capture(request):
            if request.url.split("?", 1)[0].endswith(S2B_ORDER_API_SUFFIX):
                authorization = request.headers.get("authorization", "")
                if authorization.casefold().startswith("bearer "):
                    captured["token"] = authorization[7:].strip()

        page.on("request", capture)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

    if not captured.get("token"):
        raise S2BLocalLoginRequired(
            f"未能刷新S2B {account_name}授权；请确认订单列表已经正常显示"
        )
    return captured["token"]


def _find_s2b_page(browser):
    pages = [page for context in browser.contexts for page in context.pages]
    matches = [page for page in pages if "s2bdiy.com" in page.url]
    if matches:
        page = matches[-1]
        if "/factory/orderManage" not in page.url and "/login" not in page.url:
            page.goto(S2B_ORDER_URL, wait_until="domcontentloaded")
        return page
    page = browser.contexts[0].new_page()
    page.goto(S2B_ORDER_URL, wait_until="domcontentloaded")
    return page
