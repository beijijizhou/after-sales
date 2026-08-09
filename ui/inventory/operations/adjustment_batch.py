import pandas as pd


def apply_adjustment_batch_fields(rows, business_date, action):
    """Apply one business date and action to every row in an adjustment batch."""
    result = pd.DataFrame(rows).copy()
    result["日期"] = business_date
    result["操作"] = action
    return result
