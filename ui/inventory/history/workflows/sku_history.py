"""SKU import details and exact-SKU operation history."""

import streamlit as st

from ui.inventory.history.core.batches import add_sku_batch_key
from ui.inventory.history.core.tables import (
    render_movement_table,
    render_sku_import_table,
)
from ui.inventory.i18n import t


def render_selected_sku_import(rows, selected_batch, visible_sizes=None):
    rows = add_sku_batch_key(rows)
    render_sku_import_table(
        rows[rows["batch_key"] == selected_batch], visible_sizes
    )


def render_sku_operation_history(inventory_df, history_data, visible_sizes=None):
    st.subheader(t("SKU 操作历史"))
    st.caption(t("选择一个完整 SKU，查看它的全部库存操作时间线。"))
    identity = ["category", "brand", "material", "color", "size"]
    if inventory_df.empty or not set(identity).issubset(inventory_df.columns):
        st.info(t("暂无相关记录"))
        return
    skus = inventory_df[identity].fillna("").astype(str).drop_duplicates()
    records = skus.to_dict("records")
    labels = {
        index: " · ".join(
            value or t("未填写") for value in (
                row["category"], row["brand"], row["material"],
                row["color"], row["size"],
            )
        ) for index, row in enumerate(records)
    }
    selected_index = st.selectbox(
        t("选择 SKU"), list(labels), format_func=labels.get,
        key="inventory_sku_operation_history_selection",
    )
    selected = records[selected_index]
    movements, imports, _ = history_data
    movements = _filter_exact_sku(movements, selected)
    imports = _filter_exact_sku(imports, selected)
    render_movement_table(movements, [selected["size"]])
    if not imports.empty:
        render_sku_import_table(imports, [selected["size"]])


def _filter_exact_sku(frame, selected):
    if frame.empty:
        return frame
    result = frame
    for column, value in selected.items():
        if column not in result:
            return result.iloc[0:0]
        result = result[result[column].fillna("").astype(str) == value]
    return result.reset_index(drop=True)
