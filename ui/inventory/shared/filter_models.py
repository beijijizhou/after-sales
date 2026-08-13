"""Pure inventory dimension filtering and option ordering."""

import pandas as pd

from ui.inventory.i18n import t
from utils.option_values import ordered_values


def filter_inventory_rows(df, category="", brands=None, materials=None, colors=None, sizes=None):
    if df.empty:
        return df
    result = df.copy()
    for column, values in (("category", [category] if category else None), ("brand", brands), ("material", materials), ("color", colors), ("size", sizes)):
        if values and column in result.columns:
            result = result[result[column].isin(values)]
    return result.reset_index(drop=True)


def build_inventory_filter_title(category="", brands=None, materials=None, colors=None, sizes=None):
    parts = [t(category) if category else t("全部品类")]
    for values in (brands, materials, colors, sizes):
        if values:
            parts.append("/".join(t(str(value)) for value in values))
    return " · ".join(filter(None, parts))


def normalize_dimensions(dimensions):
    columns = ["department", "category", "brand", "material", "color", "size"]
    result = pd.DataFrame(dimensions).copy()
    for column in columns:
        if column not in result.columns:
            result[column] = ""
        result[column] = result[column].fillna("").astype(str).str.strip()
    return result[columns]


def ordered_options(values, preferred, include_missing=True):
    return ordered_values(
        values, preferred, include_missing=include_missing
    )
