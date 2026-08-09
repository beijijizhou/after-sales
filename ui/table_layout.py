def fit_table_height(rows, *, minimum_rows=1, row_height=35):
    """Return a grid height that shows every row without inner scrolling."""
    row_count = len(rows) if rows is not None else 0
    visible_rows = max(int(row_count), int(minimum_rows))
    return 38 + visible_rows * int(row_height)
