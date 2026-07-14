import streamlit as st

from db.inventory import load_inventory_movements
from db.inventory.adjustments import reverse_inventory_batch
from db.inventory.sku import load_sku_imports
from ui.inventory.history_batches import (
    add_movement_batch_key,
    add_sku_batch_key,
    build_movement_batches,
    render_batch_selector,
)
from ui.inventory.history_tables import (
    render_movement_table,
    render_sku_import_table,
)
from utils.auth import get_current_operator_name, has_permission
from ui.inventory.i18n import t


def render_selected_sku_import(dated_sku_import_df, selected_batch):
    dated_sku_import_df = add_sku_batch_key(dated_sku_import_df)
    render_sku_import_table(dated_sku_import_df[dated_sku_import_df["batch_key"] == selected_batch])


def render_selected_movement(
    supabase, dated_movement_df, selected_batch, allow_undo=True
):
    dated_movement_df = add_movement_batch_key(dated_movement_df)
    selected_df = dated_movement_df[dated_movement_df["batch_key"] == selected_batch]
    render_movement_table(selected_df)
    reversed_ids = set()
    if "reversal_of_batch_id" in dated_movement_df.columns:
        reversed_ids = set(
            dated_movement_df["reversal_of_batch_id"].dropna().astype(str)
        )
    if allow_undo:
        render_movement_undo(supabase, selected_df, reversed_ids)


def render_movement_undo(supabase, selected_df, reversed_ids):
    if selected_df.empty or not has_permission("can_edit_inventory"):
        return
    if "batch_id" not in selected_df.columns or selected_df["batch_id"].isna().all():
        st.caption(t("运行最新版库存 SQL 后，才可以撤销这笔旧记录。"))
        return
    if "reversal_of_batch_id" in selected_df.columns and selected_df[
        "reversal_of_batch_id"
    ].notna().any():
        st.caption(t("这是撤销记录，不能再次撤销。"))
        return

    batch_id = str(selected_df.iloc[0]["batch_id"])
    if batch_id in reversed_ids:
        st.success(t("这笔库存变动已撤销"))
        return
    confirmed = st.checkbox(
        t("我确认撤销这笔库存变动"),
        key=f"confirm_inventory_undo_{batch_id}",
    )
    if st.button(t("撤销这笔库存变动"), disabled=not confirmed, use_container_width=True):
        row = selected_df.iloc[0]
        username = get_current_operator_name()
        try:
            reverse_inventory_batch(
                supabase,
                batch_id,
                row["department"],
                row["category"],
                username,
            )
        except Exception as error:
            st.error(f"{t('撤销失败')}: {error}")
            return
        st.session_state["inventory_saved_message"] = t(
            "库存变动已撤销，库存明细已恢复"
        )
        st.rerun()


def load_inventory_history_data(supabase, department):
    movement_df = load_inventory_movements(supabase, department, "", limit=500)
    sku_import_df = load_sku_imports(supabase, department, "", limit=500)
    batch_df = build_movement_batches(movement_df, sku_import_df)
    return movement_df, sku_import_df, batch_df


def filter_history_batches(batch_df, mode):
    normal_df = batch_df[batch_df["记录类别"] == "库存表格记录"]
    daily_mask = normal_df["备注"].fillna("").str.contains(
        "每日正常出货|每日出货|黑白短袖出库", regex=True
    )
    if mode == "daily":
        return normal_df[daily_mask]
    if mode == "regular":
        return normal_df[(normal_df["类型"] != "新增 SKU") & ~daily_mask]
    if mode == "sku":
        return normal_df[normal_df["类型"] == "新增 SKU"]
    return normal_df[normal_df["类型"] != "新增 SKU"]


def render_inventory_history(supabase, department, mode, history_data=None):
    movement_df, sku_import_df, batch_df = history_data or load_inventory_history_data(
        supabase, department
    )
    if batch_df.empty:
        st.info(t("暂无相关记录"))
        return

    selected_df = filter_history_batches(batch_df, mode)

    render_history_tab(
        supabase,
        selected_df,
        movement_df,
        sku_import_df,
        f"inventory_{mode}_history_batch",
        allow_undo=mode == "undo",
    )
    if mode == "undo":
        st.subheader(t("撤销记录"))
        reversal_df = batch_df[batch_df["记录类别"] == "撤销记录"]
        render_history_tab(
            supabase,
            reversal_df,
            movement_df,
            sku_import_df,
            "inventory_reversal_batch",
            allow_undo=False,
        )


def render_history_tab(
    supabase, batch_df, movement_df, sku_import_df, key, allow_undo=False
):
    selected_batch = render_batch_selector(batch_df, key=key)
    if not selected_batch:
        return

    selected_batch_df = batch_df[batch_df["batch_key"] == selected_batch]
    selected_type = selected_batch_df.iloc[0]["类型"] if not selected_batch_df.empty else ""
    if selected_type == "新增 SKU":
        render_selected_sku_import(sku_import_df, selected_batch)
        return

    render_selected_movement(
        supabase, movement_df, selected_batch, allow_undo=allow_undo
    )
