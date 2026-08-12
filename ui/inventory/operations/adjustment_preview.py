import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS
from ui.table_layout import fit_table_height
from utils.sku_sorting import sort_sku_rows
from ui.inventory.operations.adjustment_editor import (
    build_adjustment_preview,
    render_adjustment_preview_editor,
)
from ui.inventory.operations.inventory_review import (
    COMPARISON_COLUMNS,
    build_inventory_change_comparison,
    format_signed as _format_signed,
    render_inventory_change_comparison,
)


def build_adjustment_stock_comparison(inventory_df, edited_df, action):
    """Build one review row per edited SKU: current + change = result."""
    inventory = pd.DataFrame(inventory_df).copy()
    edited = pd.DataFrame(edited_df).copy()
    if edited.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)
    if {"型号", "数量"}.issubset(edited.columns):
        return _build_model_stock_comparison(inventory, edited, action)

    identity = ["品牌", "材质", "颜色"]
    for frame in [inventory, edited]:
        for column in identity:
            if column not in frame:
                frame[column] = ""
            frame[column] = frame[column].fillna("").astype(str).str.strip()
        for size in SIZE_COLUMNS:
            if size not in frame:
                frame[size] = 0
            frame[size] = pd.to_numeric(
                frame[size], errors="coerce"
            ).fillna(0).astype(int)

    selected_for_setting = edited.get(
        "设置此行", pd.Series(False, index=edited.index)
    ).fillna(False).astype(bool)
    edited = edited[
        (edited["材质"] != "")
        & (edited["颜色"] != "")
        & ((edited[SIZE_COLUMNS].sum(axis=1) > 0) | selected_for_setting)
    ]
    if edited.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)

    current = inventory.groupby(
        identity, dropna=False, as_index=False
    )[SIZE_COLUMNS].sum()
    changes = edited.groupby(
        identity, dropna=False, as_index=False, sort=False
    )[SIZE_COLUMNS].sum()
    identities = sort_sku_rows(
        changes[identity], size="__wide_size_columns__"
    )
    current_by_key = current.set_index(identity)[SIZE_COLUMNS]
    changes_by_key = changes.set_index(identity)[SIZE_COLUMNS]
    direction = 1 if action == "增加" else -1
    rows = []
    for item in identities.to_dict("records"):
        key = tuple(item[column] for column in identity)
        current_values = _wide_values(current_by_key, key)
        entered_values = _wide_values(changes_by_key, key)
        for size in SIZE_COLUMNS:
            entered = int(entered_values[size])
            if entered == 0 and action != "设置":
                continue
            current_quantity = int(current_values[size])
            change = (
                entered - current_quantity
                if action == "设置" else entered * direction
            )
            rows.append({
                "材质": item["材质"],
                "品牌": item["品牌"],
                "颜色": item["颜色"],
                "尺码": size,
                "当前库存": current_quantity,
                "本次变动": change,
                "调整后库存": current_quantity + change,
                "设置为": entered if action == "设置" else pd.NA,
            })
    result_columns = [*COMPARISON_COLUMNS]
    if action == "设置":
        result_columns.append("设置为")
    return sort_sku_rows(
        pd.DataFrame(rows, columns=result_columns),
        material="材质", color="颜色", size="尺码",
        leading=["材质", "品牌"],
    )

def render_adjustment_stock_comparison(inventory_df, edited_df, action):
    comparison = build_adjustment_stock_comparison(
        inventory_df, edited_df, action
    )
    if comparison.empty:
        return comparison
    if action == "设置":
        st.markdown("#### 保存前库存核对")
        st.caption("设置会将 SKU 库存直接改为盘点数；实际差额仍保留在审计流水中。")
        display = comparison.copy().rename(columns={
            "设置为": "本次设置为", "本次变动": "实际变动 (+/-)",
        })
        display["实际变动 (+/-)"] = display["实际变动 (+/-)"].map(_format_signed)
        st.dataframe(
            display[[
                "材质", "品牌", "颜色", "尺码", "当前库存",
                "本次设置为", "实际变动 (+/-)", "调整后库存",
            ]],
            hide_index=True, width="stretch", height=fit_table_height(display),
        )
        return comparison
    return render_inventory_change_comparison(comparison, action=action)


def _build_model_stock_comparison(inventory, edited, action):
    identity = ["材质", "品牌", "颜色", "型号"]
    for frame in [inventory, edited]:
        for column in identity:
            if column not in frame:
                frame[column] = ""
            frame[column] = frame[column].fillna("").astype(str).str.strip()
    edited["数量"] = pd.to_numeric(
        edited["数量"], errors="coerce"
    ).fillna(0).astype(int)
    selected_for_setting = edited.get(
        "设置此 SKU", pd.Series(False, index=edited.index)
    ).fillna(False).astype(bool)
    edited = edited[(edited["数量"] > 0) | selected_for_setting]
    if edited.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)

    current_column = next(
        (column for column in ["总库存", "数量", "quantity"] if column in inventory),
        None,
    )
    if current_column is None:
        inventory["_current_quantity"] = 0
        current_column = "_current_quantity"
    inventory[current_column] = pd.to_numeric(
        inventory[current_column], errors="coerce"
    ).fillna(0).astype(int)
    current = inventory.groupby(identity, dropna=False)[current_column].sum()
    changes = edited.groupby(identity, dropna=False, sort=False)["数量"].sum()
    direction = 1 if action == "增加" else -1
    rows = []
    for key, quantity in changes.items():
        key = key if isinstance(key, tuple) else (key,)
        current_quantity = int(current.get(key, 0))
        change = (
            int(quantity) - current_quantity
            if action == "设置" else int(quantity) * direction
        )
        rows.append({
            "材质": key[0], "品牌": key[1], "颜色": key[2],
            "尺码": key[3], "当前库存": current_quantity,
            "本次变动": change,
            "调整后库存": current_quantity + change,
            "设置为": int(quantity) if action == "设置" else pd.NA,
        })
    result_columns = [*COMPARISON_COLUMNS]
    if action == "设置":
        result_columns.append("设置为")
    return sort_sku_rows(
        pd.DataFrame(rows, columns=result_columns),
        material="材质", color="颜色", size="尺码",
        leading=["材质", "品牌"],
    )


def _wide_values(indexed, key):
    try:
        values = indexed.loc[key]
    except KeyError:
        return pd.Series(0, index=SIZE_COLUMNS, dtype="int64")
    if isinstance(values, pd.DataFrame):
        values = values.sum(axis=0)
    return pd.to_numeric(values, errors="coerce").fillna(0).astype(int)
