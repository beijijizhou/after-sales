import pandas as pd


IDENTITY_COLUMNS = ["品类", "品牌", "材质", "颜色"]


def build_sku_identity_table(inventory_df):
    if inventory_df.empty:
        return pd.DataFrame()

    source = inventory_df.copy()
    source["quantity"] = pd.to_numeric(
        source["quantity"], errors="coerce"
    ).fillna(0).astype(int)
    grouped = (
        source.groupby(
            ["category", "brand", "material", "color"],
            dropna=False,
            as_index=False,
        )
        .agg(
            尺码=("size", lambda values: " / ".join(sorted({
                str(value).strip() for value in values
                if pd.notna(value) and str(value).strip()
            }, key=_size_order))),
            总库存=("quantity", "sum"),
        )
        .rename(columns={
            "category": "品类", "brand": "品牌",
            "material": "材质", "color": "颜色",
        })
    )
    grouped.insert(0, "当前 SKU", grouped.apply(_format_identity, axis=1))
    return grouped


def build_sku_identity_changes(original_df, edited_df):
    rows = []
    for index, original in original_df.reset_index(drop=True).iterrows():
        edited = edited_df.reset_index(drop=True).iloc[index]
        old_values = [_clean(original[column]) for column in IDENTITY_COLUMNS]
        new_values = [_clean(edited[column]) for column in IDENTITY_COLUMNS]
        if old_values == new_values:
            continue
        if not new_values[2] or not new_values[3]:
            raise ValueError("材质和颜色不能为空")
        rows.append({
            **{f"old_{key}": value for key, value in zip(
                ["category", "brand", "material", "color"], old_values
            )},
            **{f"new_{key}": value for key, value in zip(
                ["category", "brand", "material", "color"], new_values
            )},
        })
    return rows


def update_sku_identities(
    supabase, department, changes, changed_by="system"
):
    response = supabase.rpc(
        "update_inventory_sku_identities",
        {
            "p_department": department,
            "p_changes": changes,
            "p_changed_by": changed_by,
        },
    ).execute()
    return int(response.data or 0)


def _format_identity(row):
    category = _clean(row.get("品类")) or "未分类"
    brand = _clean(row.get("品牌")) or "无品牌"
    return " · ".join([
        category, brand, _clean(row.get("材质")), _clean(row.get("颜色"))
    ])


def _clean(value):
    return "" if pd.isna(value) else str(value).strip()


def _size_order(value):
    order = {size: index for index, size in enumerate(
        ["S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]
    )}
    return order.get(str(value), 99), str(value)
