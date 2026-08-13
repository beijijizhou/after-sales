PAGE_SIZE = 1000


def fetch_range_pages(fetch_page, limit, page_size=PAGE_SIZE):
    unbounded = limit is None
    requested = None if unbounded else max(int(limit or 0), 0)
    if requested == 0:
        return []
    rows = []
    while unbounded or len(rows) < requested:
        start = len(rows)
        end = (
            start + page_size - 1
            if unbounded
            else min(start + page_size, requested) - 1
        )
        page = list(fetch_page(start, end) or [])
        rows.extend(page)
        if len(page) < end - start + 1:
            break
    return rows if unbounded else rows[:requested]
