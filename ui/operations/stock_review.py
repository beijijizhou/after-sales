"""One three-stage stock review for every inventory-writing workflow."""

import pandas as pd
import streamlit as st

from ui.table_layout import fit_table_height


def prepare_stock_change_display(comparison, action=None):
    result = pd.DataFrame(comparison).copy()
    if result.empty:
        return result, "本次变动 (+/-)"
    # A workflow may carry both base-unit and package-unit audit columns.
    # Older adapters could normalize both sets to the same display label,
    # leaving pandas with duplicate columns.  Selecting one of those labels
    # then returns a DataFrame instead of a Series and crashes the whole
    # Streamlit page during numeric conversion.  The workflow adapter owns
    # which unit is canonical; this shared rendering boundary guarantees that
    # an accidental duplicate cannot take down any inventory-writing page.
    if not result.columns.is_unique:
        result = result.loc[:, ~result.columns.duplicated(keep="first")].copy()
    for column in ["当前库存", "本次变动", "调整后库存"]:
        if column not in result:
            raise ValueError(f"库存核对缺少字段：{column}")
        result[column] = pd.to_numeric(
            result[column], errors="coerce"
        ).fillna(0)
    if action is None:
        directions = {
            "增加" if value > 0 else "扣减"
            for value in result["本次变动"] if value != 0
        }
        action = directions.pop() if len(directions) == 1 else "变动"
    operation_column = {
        "增加": "本次入库 (+)",
        "入库": "本次入库 (+)",
        "减少": "本次出库 (-)",
        "扣减": "本次出库 (-)",
        "出库": "本次出库 (-)",
        "领用": "本次出库 (-)",
    }.get(action, "本次变动 (+/-)")
    return result.rename(columns={"本次变动": operation_column}), operation_column


def render_stock_change_review(
    comparison,
    *,
    action=None,
    title="保存前库存核对",
    identity_columns=None,
    extra_columns=None,
    unit=None,
    unit_column=None,
    quantity_format="%.2f",
):
    display, operation_column = prepare_stock_change_display(
        comparison, action=action
    )
    if display.empty:
        return pd.DataFrame(comparison).copy()
    st.markdown(f"#### {title}")
    st.caption("每行代表一个 SKU；当前库存 + 本次变动 = 调整后库存。")
    negative = display["调整后库存"] < 0
    if negative.any():
        st.error(f"有 {int(negative.sum())} 个 SKU 调整后会出现负库存。")
    identity_columns = identity_columns or []
    extra_columns = extra_columns or []
    columns = [
        *[column for column in identity_columns if column in display],
        "当前库存", operation_column, "调整后库存",
        *[column for column in extra_columns if column in display],
    ]
    suffix = f" {unit}" if unit else ""
    config = {
        "当前库存": st.column_config.NumberColumn(
            format=f"{quantity_format}{suffix}"
        ),
        operation_column: st.column_config.NumberColumn(
            format=f"{quantity_format}{suffix}"
        ),
        "调整后库存": st.column_config.NumberColumn(
            format=f"{quantity_format}{suffix}"
        ),
    }
    if unit_column and unit_column in display:
        config[unit_column] = st.column_config.TextColumn("单位")
    st.dataframe(
        display[columns], hide_index=True, width="stretch",
        height=fit_table_height(display), column_config=config,
    )
    return pd.DataFrame(comparison).copy()


def format_signed(value):
    number = int(value)
    return f"+{number:,}" if number > 0 else f"{number:,}"
