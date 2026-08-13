"""SKU editor wide-table transformations and catalog presentation."""

from hashlib import sha1

import pandas as pd

from db.inventory import SIZE_COLUMNS
from ui.inventory.i18n import t


def uses_standard_sku_sizes(source):
    specifications = {
        str(value).strip() for value in pd.DataFrame(source).get("规格", [])
        if not pd.isna(value) and str(value).strip()
    }
    return bool(specifications) and specifications.issubset(set(SIZE_COLUMNS))


def build_sku_editor_wide_source(source):
    dimensions = ["category", "brand", "material", "color", "unit", "is_active"]
    prepared = pd.DataFrame(source).copy()
    prepared[dimensions[:-1]] = prepared[dimensions[:-1]].fillna("")
    prepared["is_active"] = prepared["is_active"].fillna(True).astype(bool)
    sizes = [
        size for size in SIZE_COLUMNS
        if size in set(prepared["规格"].dropna().astype(str))
    ]
    rows = []
    for keys, group in prepared.groupby(dimensions, dropna=False, sort=False):
        row = dict(zip(dimensions, keys))
        row["_group_key"] = sku_editor_group_key(group)
        quantities = group.groupby("规格")["quantity"].sum().to_dict()
        row.update({size: quantities.get(size, pd.NA) for size in sizes})
        rows.append(row)
    return pd.DataFrame(rows, columns=["_group_key", *dimensions, *sizes])


def expand_sku_editor_wide_rows(source, edited):
    dimensions = ["category", "brand", "material", "color", "unit", "is_active"]
    prepared = pd.DataFrame(source).copy()
    prepared[dimensions[:-1]] = prepared[dimensions[:-1]].fillna("")
    prepared["is_active"] = prepared["is_active"].fillna(True).astype(bool)
    group_keys = {}
    for _, group in prepared.groupby(dimensions, dropna=False, sort=False):
        key = sku_editor_group_key(group)
        group_keys.update({item_id: key for item_id in group["id"]})
    prepared["_group_key"] = prepared["id"].map(group_keys)
    changes = pd.DataFrame(edited)[["_group_key", *dimensions]]
    return prepared.drop(columns=dimensions).merge(
        changes, on="_group_key", how="left", validate="many_to_one"
    ).drop(columns="_group_key")


def sku_editor_group_key(group):
    identifiers = sorted(str(value) for value in group["id"])
    return sha1("|".join(identifiers).encode()).hexdigest()[:12]


def filter_sku_editor_source(source, selections=None):
    result = source.copy()
    selections = selections or {}
    if selections.get("category") != "手机壳" and "category" in result:
        result = result[result["category"] != "手机壳"]
    for field, value in selections.items():
        if isinstance(value, (list, tuple, set)) and value:
            result = result[result[field].isin(value)]
        elif value and value != "全部":
            result = result[result[field].fillna("").astype(str).str.strip() == value]
    return result.reset_index(drop=True)


def display_catalog(catalog):
    source = catalog.assign(规格=catalog["model"].fillna(catalog["size"]))
    specifications = set(source["规格"].dropna().astype(str))
    if specifications and specifications.issubset(set(SIZE_COLUMNS)):
        index = ["category", "brand", "material", "color", "unit", "is_active"]
        source[index] = source[index].fillna("")
        result = source.groupby(
            [*index, "规格"], dropna=False, sort=False
        )["quantity"].sum().unstack(fill_value=0).reset_index()
        for size in SIZE_COLUMNS:
            if size not in result:
                result[size] = 0
        result = result.rename(columns={
            "category": t("品类"), "brand": t("品牌"), "material": t("材质"),
            "color": t("颜色"), "unit": t("单位"), "is_active": t("状态"),
        })
        result[t("状态")] = result[t("状态")].map({True: t("启用"), False: t("停用")})
        return result[[t(value) for value in ["品类", "品牌", "材质", "颜色", "单位", "状态"]] + SIZE_COLUMNS]
    result = source.rename(columns={
        "category": t("品类"), "brand": t("品牌"), "material": t("材质"),
        "color": t("颜色"), "规格": t("规格"), "unit": t("单位"),
        "quantity": t("当前库存"), "is_active": t("状态"),
    })
    result[t("状态")] = result[t("状态")].map({True: t("启用"), False: t("停用")})
    return result[[t(value) for value in [
        "品类", "品牌", "材质", "颜色", "规格", "单位", "当前库存", "状态",
    ]]]
