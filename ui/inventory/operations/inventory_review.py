"""Shared before/change/after inventory review used by every stock writer."""

import pandas as pd
import streamlit as st

from ui.table_layout import fit_table_height
from utils.sku_sorting import sort_sku_rows


COMPARISON_COLUMNS = [
    "材质", "品牌", "颜色", "尺码", "当前库存", "本次变动", "调整后库存",
]


def build_inventory_change_comparison(inventory_df, adjustment_df):
    inventory = pd.DataFrame(inventory_df).rename(columns={
        "department": "部门", "category": "品类", "brand": "品牌",
        "material": "材质", "color": "颜色", "size": "尺码",
        "quantity": "当前库存", "总库存": "当前库存", "型号": "尺码",
    }).copy()
    changes = pd.DataFrame(adjustment_df).rename(columns={
        "department": "部门", "category": "品类", "brand": "品牌",
        "material": "材质", "color": "颜色", "size": "尺码",
        "quantity": "数量",
    }).copy()
    if changes.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)
    identity = [
        column for column in ["部门", "品类", "材质", "品牌", "颜色", "尺码"]
        if column in changes.columns
    ]
    if not {"材质", "品牌", "颜色", "尺码"}.issubset(identity):
        return pd.DataFrame(columns=COMPARISON_COLUMNS)
    for frame in [inventory, changes]:
        for column in identity:
            if column not in frame:
                frame[column] = ""
            frame[column] = frame[column].fillna("").astype(str).str.strip()
    changes["数量"] = pd.to_numeric(
        changes.get("数量", pd.Series(0, index=changes.index)), errors="coerce"
    ).fillna(0).astype(int)
    if "操作" in changes:
        direction = changes["操作"].map(
            {"增加": 1, "减少": -1, "扣减": -1}
        ).fillna(0)
        changes["本次变动"] = changes["数量"] * direction.astype(int)
    elif "quantity_change" in changes:
        changes["本次变动"] = pd.to_numeric(
            changes["quantity_change"], errors="coerce"
        ).fillna(0).astype(int)
    else:
        changes["本次变动"] = changes["数量"]
    changes = changes[changes["本次变动"] != 0]
    if changes.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)
    inventory["当前库存"] = pd.to_numeric(
        inventory.get("当前库存", pd.Series(0, index=inventory.index)),
        errors="coerce",
    ).fillna(0).astype(int)
    current = inventory.groupby(identity, dropna=False)["当前库存"].sum()
    grouped = changes.groupby(
        identity, dropna=False, sort=False
    )["本次变动"].sum()
    rows = []
    for key, change in grouped.items():
        key = key if isinstance(key, tuple) else (key,)
        current_quantity = int(current.get(key, 0))
        rows.append({
            **dict(zip(identity, key)), "当前库存": current_quantity,
            "本次变动": int(change),
            "调整后库存": current_quantity + int(change),
        })
    columns = [
        *[column for column in ["部门", "品类"] if column in identity],
        *COMPARISON_COLUMNS,
    ]
    return sort_sku_rows(
        pd.DataFrame(rows, columns=columns), material="材质",
        color="颜色", size="尺码",
        leading=[
            column for column in ["部门", "品类", "材质", "品牌"]
            if column in columns
        ],
    )


def render_inventory_change_comparison(
    comparison, *, action=None, title="保存前库存核对", unit="件",
):
    comparison = pd.DataFrame(comparison).copy()
    if comparison.empty:
        return comparison
    if action is None:
        directions = {
            "增加" if int(value) > 0 else "扣减"
            for value in comparison["本次变动"] if int(value) != 0
        }
        action = directions.pop() if len(directions) == 1 else "变动"
    operation_column = {
        "增加": "本次入库 (+)", "减少": "本次出库 (-)",
        "扣减": "本次出库 (-)",
    }.get(action, "本次变动 (+/-)")
    st.markdown(f"#### {title}")
    st.caption("每行代表一个 SKU；当前库存 + 本次变动 = 调整后库存。")
    negative = comparison["调整后库存"] < 0
    if negative.any():
        st.error(f"有 {int(negative.sum())} 个 SKU 调整后会出现负库存。")
    display = comparison.rename(columns={"本次变动": operation_column})
    display[operation_column] = display[operation_column].map(format_signed)
    st.dataframe(
        display, hide_index=True, width="stretch",
        height=fit_table_height(display),
        column_config={
            "当前库存": st.column_config.NumberColumn(format=f"%d {unit}"),
            "调整后库存": st.column_config.NumberColumn(format=f"%d {unit}"),
        },
    )
    return comparison


def format_signed(value):
    number = int(value)
    return f"+{number:,}" if number > 0 else f"{number:,}"
