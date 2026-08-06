import pandas as pd
import streamlit as st

from db.inventory import load_inventory_movements, normalize_adjustment_rows
from db.inventory.operations.adjustments import reverse_inventory_batch
from db.inventory.operations.outbound_audit import (
    DAILY_OUTBOUND_REASONS,
    audit_outbound_batch,
    build_daily_outbound_edit_rows,
    build_replacement_inventory,
    find_outbound_inventory_issues,
    load_daily_outbound_batch,
    load_outbound_inventory,
    replace_daily_outbound_batch,
)
from db.inventory.sku import load_sku_imports
from ui.inventory.history.history_batches import (
    add_movement_batch_key,
    add_sku_batch_key,
    build_movement_batches,
    render_batch_selector,
)
from ui.inventory.history.history_tables import (
    render_movement_table,
    render_sku_import_table,
)
from ui.inventory.operations.adjustment_preview import (
    render_adjustment_preview_editor,
)
from ui.inventory.history.history_filters import (
    filter_batches_by_movement_type,
    filter_batches_by_outbound_kind,
    filter_history_batches,
    filter_reversal_scope,
)
from utils.auth import get_current_operator_name, has_permission
from ui.inventory.i18n import t
from ui.inventory.shared import filter_inventory_rows


def render_selected_sku_import(
    dated_sku_import_df, selected_batch, visible_sizes=None
):
    dated_sku_import_df = add_sku_batch_key(dated_sku_import_df)
    render_sku_import_table(
        dated_sku_import_df[dated_sku_import_df["batch_key"] == selected_batch],
        visible_sizes,
    )


def render_selected_movement(
    supabase, dated_movement_df, selected_batch, allow_undo=True,
    visible_sizes=None,
):
    dated_movement_df = add_movement_batch_key(dated_movement_df)
    selected_df = dated_movement_df[dated_movement_df["batch_key"] == selected_batch]
    render_movement_table(selected_df, visible_sizes)
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
    batch_ids = selected_df["batch_id"].dropna().astype(str).unique()
    if len(batch_ids) > 1:
        st.caption(
            "这是一笔由旧版系统拆分保存的自动消耗记录，"
            "已合并展示；不能使用单批次撤销。"
        )
        return
    if "reversal_of_batch_id" in selected_df.columns and selected_df[
        "reversal_of_batch_id"
    ].notna().any():
        st.caption(t("这是撤销记录，不能再次撤销。"))
        return

    batch_id = batch_ids[0]
    if batch_id in reversed_ids:
        st.success(t("这笔库存变动已撤销"))
        return
    if _is_editable_daily_outbound(selected_df):
        action = st.segmented_control(
            "处理方式",
            ["修改并替换", "仅撤销"],
            default="修改并替换",
            key=f"inventory_batch_action_{batch_id}",
        )
        if action == "修改并替换":
            _render_daily_outbound_replacement(supabase, batch_id)
            return
    confirmed = st.checkbox(
        t("我确认撤销这笔库存变动"),
        key=f"confirm_inventory_undo_{batch_id}",
    )
    if st.button(t("撤销这笔库存变动"), disabled=not confirmed, width="stretch"):
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


def _is_editable_daily_outbound(selected_df):
    if selected_df.empty:
        return False
    reasons = selected_df["reason"].fillna("").astype(str)
    quantities = pd.to_numeric(
        selected_df["quantity_change"], errors="coerce"
    ).fillna(0)
    return reasons.isin(DAILY_OUTBOUND_REASONS).all() and quantities.lt(0).all()


def _render_daily_outbound_replacement(supabase, batch_id):
    st.markdown("#### 修改每日出库记录")
    st.caption(
        "保存时会自动撤销原批次并生成修正版批次；"
        "原记录和撤销记录都会保留。编辑器始终读取该批次的全部 SKU，"
        "不受上方筛选条件影响。"
    )
    try:
        complete_batch_df = load_daily_outbound_batch(supabase, batch_id)
    except Exception as error:
        st.error(f"读取完整出库批次失败：{error}")
        return
    if complete_batch_df.empty:
        st.error("没有找到这笔出库批次，可能已被其他用户处理。")
        return
    if not _is_editable_daily_outbound(complete_batch_df):
        st.error("完整批次不是可修改的每日出库记录，请刷新后重试。")
        return

    original = build_daily_outbound_edit_rows(complete_batch_df)
    edited_wide = render_adjustment_preview_editor(
        original,
        key=f"daily_outbound_replacement_{batch_id}",
        lock_operation=True,
        lock_identity=False,
        allow_rows=True,
        disabled_columns=["备注"],
    )
    corrected = normalize_adjustment_rows(edited_wide)
    if corrected.empty:
        st.warning("修正版不能为空；如果要删除整笔记录，请选择“仅撤销”。")
        return
    original_dates = pd.to_datetime(
        original["日期"], errors="coerce"
    ).dt.date.dropna().unique()
    if len(original_dates) != 1:
        st.error("这笔批次包含多个出库日期，暂时不能在每日出库编辑器中修改。")
        return
    if not corrected["日期"].eq(original_dates[0]).all():
        st.error(f"出库日期必须保持为 {original_dates[0]}。")
        return
    corrected["备注"] = "仓库每日出货"
    original_total = int(original["数量"].sum())
    corrected_total = int(corrected["数量"].sum())
    columns = st.columns(3)
    columns[0].metric("原出库", f"{original_total:,} 件")
    columns[1].metric("修正后", f"{corrected_total:,} 件")
    columns[2].metric(
        "变化", f"{corrected_total - original_total:+,} 件"
    )
    row = complete_batch_df.iloc[0]
    try:
        current_inventory = load_outbound_inventory(
            supabase, row["department"], row["category"]
        )
        replacement_inventory = build_replacement_inventory(
            current_inventory, complete_batch_df
        )
        issues = find_outbound_inventory_issues(
            corrected, replacement_inventory
        )
    except Exception as error:
        st.error(f"修正版库存检查失败：{error}")
        return
    if not issues.empty:
        st.error("修正版包含不存在的 SKU 或撤销原批次后仍然库存不足。")
        st.dataframe(issues, hide_index=True, width="stretch")
        return
    confirmed = st.checkbox(
        "我已核对修正版，并确认撤销原批次后生成新批次",
        key=f"confirm_daily_outbound_replacement_{batch_id}",
    )
    if not st.button(
        "保存修正版",
        type="primary",
        width="stretch",
        disabled=not confirmed,
        key=f"save_daily_outbound_replacement_{batch_id}",
    ):
        return
    username = get_current_operator_name()
    try:
        replacement_batch_id = replace_daily_outbound_batch(
            supabase, batch_id, row["department"], row["category"],
            complete_batch_df, corrected, username,
        )
        audit, mismatches = audit_outbound_batch(
            supabase, replacement_batch_id, corrected
        )
    except Exception as error:
        st.error(f"修改每日出库失败：{error}")
        return
    if not audit["passed"]:
        st.error("修正版已写入，但自动核验未通过，请立即查看差异。")
        st.dataframe(mismatches, hide_index=True, width="stretch")
        return
    st.session_state["inventory_saved_message"] = (
        f"每日出库已修改：{original_total:,} → {corrected_total:,} 件"
    )
    st.rerun()


def load_inventory_history_data(supabase, department, limit=500):
    movement_df = load_inventory_movements(
        supabase, department, "", limit=limit
    )
    sku_import_df = load_sku_imports(
        supabase, department, "", limit=limit
    )
    batch_df = build_movement_batches(movement_df, sku_import_df)
    return movement_df, sku_import_df, batch_df


def filter_inventory_history_data(
    history_data, category, brands, materials, colors, sizes,
):
    movement_df, sku_import_df, _ = history_data
    movement_df = filter_inventory_rows(
        movement_df, category, brands, materials, colors, sizes
    )
    sku_import_df = filter_inventory_rows(
        sku_import_df, category, brands, materials, colors, sizes
    )
    batch_df = build_movement_batches(movement_df, sku_import_df)
    return movement_df, sku_import_df, batch_df


def render_inventory_history(
    supabase, department, mode, history_data=None, visible_sizes=None,
    movement_types=None,
):
    movement_df, sku_import_df, batch_df = history_data or load_inventory_history_data(
        supabase, department
    )
    if batch_df.empty:
        st.info(t("暂无相关记录"))
        return

    selected_df = filter_history_batches(batch_df, mode)
    history_key = f"inventory_{mode}_history_batch"
    if mode == "all":
        outbound_kind = st.selectbox(
            t("流水记录类型"),
            [
                "全部流水", "货柜入库", "每日库存扣减",
                "临时出库",
            ],
            format_func=t,
            key="inventory_ledger_outbound_kind",
        )
        selected_df = filter_batches_by_outbound_kind(
            selected_df, outbound_kind
        )
    if mode == "undo":
        st.caption(
            "这里显示当前部门的完整可撤销批次，不受库存日期、品类、"
            "品牌、材质、颜色或尺码筛选影响。"
        )
        reversal_scope = st.segmented_control(
            "撤销记录类型",
            [
                "全部可撤销记录", "仓库每日出库", "系统库存扣减",
                "临时库存调整", "其他出入库",
            ],
            default="全部可撤销记录",
            key="inventory_reversal_scope",
        ) or "全部可撤销记录"
        selected_df = filter_reversal_scope(
            selected_df, reversal_scope
        )
        st.caption(
            f"{reversal_scope}：当前显示 {len(selected_df):,} 笔可撤销记录"
        )
        history_key = (
            "inventory_undo_history_batch_"
            + reversal_scope
        )
    elif mode != "sku":
        selected_df = filter_batches_by_movement_type(
            selected_df, movement_types
        )

    if mode == "sku":
        st.subheader(t("SKU 导入历史"))

    render_history_tab(
        supabase,
        selected_df,
        movement_df,
        sku_import_df,
        history_key,
        allow_undo=mode == "undo",
        visible_sizes=visible_sizes,
        sku_import=mode == "sku",
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
            value or t("未填写")
            for value in [
                row["category"], row["brand"], row["material"],
                row["color"], row["size"],
            ]
        )
        for index, row in enumerate(records)
    }
    selected_index = st.selectbox(
        t("选择 SKU"), list(labels), format_func=labels.get,
        key="inventory_sku_operation_history_selection",
    )
    selected = records[selected_index]
    movement_df, sku_import_df, _ = history_data
    movement_df = _filter_exact_sku(movement_df, selected)
    sku_import_df = _filter_exact_sku(sku_import_df, selected)
    render_movement_table(movement_df, [selected["size"]])
    if not sku_import_df.empty:
        render_sku_import_table(sku_import_df, [selected["size"]])


def _filter_exact_sku(df, selected):
    if df.empty:
        return df
    result = df
    for column, value in selected.items():
        if column not in result.columns:
            return result.iloc[0:0]
        result = result[
            result[column].fillna("").astype(str) == value
        ]
    return result.reset_index(drop=True)
    if mode == "undo":
        st.subheader(t("撤销记录"))
        reversal_df = batch_df[batch_df["记录类别"] == "撤销记录"]
        reversal_df = filter_batches_by_movement_type(
            reversal_df, movement_types
        )
        render_history_tab(
            supabase,
            reversal_df,
            movement_df,
            sku_import_df,
            "inventory_reversal_batch",
            allow_undo=False,
            visible_sizes=visible_sizes,
        )


def render_history_tab(
    supabase, batch_df, movement_df, sku_import_df, key, allow_undo=False,
    visible_sizes=None, sku_import=False,
):
    selected_batch = render_batch_selector(
        batch_df, key=key, sku_import=sku_import
    )
    if not selected_batch:
        return

    selected_batch_df = batch_df[batch_df["batch_key"] == selected_batch]
    selected_type = selected_batch_df.iloc[0]["类型"] if not selected_batch_df.empty else ""
    if selected_type == "新增 SKU":
        render_selected_sku_import(sku_import_df, selected_batch, visible_sizes)
        return

    render_selected_movement(
        supabase, movement_df, selected_batch, allow_undo=allow_undo,
        visible_sizes=visible_sizes,
    )
