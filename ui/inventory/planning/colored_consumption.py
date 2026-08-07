import pandas as pd
import streamlit as st

from db.inventory.core.constants import SIZE_COLUMNS
from automation.sync.dtf_colored_inventory import (
    apply_colored_daily_deduction,
    build_colored_reconciliation_backlog,
    build_colored_consumption_wide_table,
    build_colored_daily_preview,
    load_colored_day_deducted_total,
    load_colored_consumption_history,
)
from utils.auth.session import get_current_operator_name, has_permission
from ui.inventory.shared.filters import _reset_invalid_selectbox


def render_colored_consumption(supabase, current_date, inventory_df):
    st.subheader("彩色短袖每日消耗")
    st.caption(
        "按最近 14 天的有效生产日计算；快速补录平台数据会立即进入模型，"
        "全平台数据到齐后会用同一天的最新数据重新计算。"
    )
    history = load_colored_consumption_history(supabase, current_date, 14)
    if history.empty:
        st.info("最近 14 天暂无已同步的彩色短袖生产消耗")
    else:
        stock = _stock_summary(inventory_df)
        display = history.merge(stock, on=["颜色", "尺码"], how="left")
        display["当前库存"] = display["当前库存"].fillna(0).astype(int)
        display["可撑天数"] = display.apply(
            lambda row: row["当前库存"] / row["每日消耗"]
            if row["每日消耗"] > 0 else None,
            axis=1,
        )
        total = history["每日消耗"].sum()
        days = int(history["有效天数"].max())
        left, right = st.columns(2)
        left.metric("一天消耗", f"{total:,.1f} 件")
        right.metric("有效生产日", f"{days} 天")
        wide = build_colored_consumption_wide_table(display)
        st.dataframe(
            wide, hide_index=True, width="stretch",
            column_config={
                size: st.column_config.NumberColumn(size, format="%.1f")
                for size in SIZE_COLUMNS
            },
        )
    _render_colored_reconciliation(supabase, current_date)


def _render_colored_reconciliation(supabase, current_date):
    st.divider()
    st.subheader("彩色短袖待核对差异")
    st.caption(
        "每日快速出库只执行一次；库存不足、SKU 未匹配和未读取平台在这里单独处理。"
    )
    try:
        backlog = build_colored_reconciliation_backlog(
            supabase, current_date, 14
        )
    except Exception as error:
        st.error(f"彩色短袖待核对差异加载失败：{error}")
        return
    if backlog.empty:
        st.success("最近 14 天没有已出库但尚待核对的彩色短袖差异。")
        return
    st.dataframe(
        backlog, hide_index=True, width="stretch",
        column_config={
            "日期": st.column_config.DateColumn("日期"),
            "生产数据": st.column_config.NumberColumn(format="%d 件"),
            "已扣库存": st.column_config.NumberColumn(format="%d 件"),
            "当前可补扣": st.column_config.NumberColumn(format="%d 件"),
            "库存/SKU待核对": st.column_config.NumberColumn(format="%d 件"),
            "尚未读取平台": st.column_config.TextColumn(width="large"),
            "状态": st.column_config.TextColumn(width="medium"),
        },
    )
    selectable = backlog[backlog["当前可补扣"] > 0]
    if selectable.empty:
        st.info("当前没有可继续扣减的差额；请先补库存、修正 SKU 或补齐平台数据。")
        return
    reconciliation_dates = selectable["日期"].tolist()
    _reset_invalid_selectbox(
        "colored_reconciliation_date", reconciliation_dates
    )
    selected_date = st.selectbox(
        "选择要处理的差异日期",
        reconciliation_dates,
        format_func=lambda value: value.strftime("%Y-%m-%d"),
        key="colored_reconciliation_date",
    )
    preview_key = "colored_reconciliation_preview"
    preview_date_key = "colored_reconciliation_preview_date"
    if st.button(
        "预览所选日期差额",
        key="colored_reconciliation_preview_button",
    ):
        st.session_state[preview_key] = build_colored_daily_preview(
            supabase, selected_date
        )
        st.session_state[preview_date_key] = selected_date
    preview = st.session_state.get(preview_key)
    if (
        preview is None
        or st.session_state.get(preview_date_key) != selected_date
    ):
        return
    st.dataframe(preview, hide_index=True, width="stretch")
    quantity = int(pd.to_numeric(
        preview.get("预计扣减", pd.Series(dtype="float64")),
        errors="coerce",
    ).fillna(0).sum())
    st.info(
        f"当前可继续扣减 {quantity:,} 件。该操作只处理差额，不会重复扣除已出库数量。"
    )
    if not has_permission("can_edit_inventory"):
        st.info("当前账号只有查看权限，不能处理库存差额。")
        return
    confirmed = st.checkbox(
        "我已核对所选日期的库存差额",
        key="colored_reconciliation_confirm",
    )
    if not st.button(
        "确认补扣所选差额",
        type="primary",
        disabled=not confirmed or quantity <= 0,
        key="colored_reconciliation_apply",
    ):
        return
    try:
        imported = apply_colored_daily_deduction(
            supabase, preview, selected_date, get_current_operator_name()
        )
    except Exception as error:
        st.error(f"彩色短袖差额补扣失败：{error}")
        return
    st.session_state.pop(preview_key, None)
    st.session_state.pop(preview_date_key, None)
    st.session_state["inventory_saved_message"] = (
        f"{selected_date:%m/%d} 彩色短袖差额已补扣 {imported:,} 件"
    )
    st.rerun()


def render_colored_daily_deduction(supabase, current_date):
    st.subheader("彩色短袖系统库存扣减")
    st.caption(
        "从全部衣服平台读取当天生产数据；按纽约日期生成批次，"
        "重复确认不会重复扣减。"
    )
    state_key = "colored_daily_deduction_preview"
    date_key = "colored_daily_deduction_date"
    deducted = load_colored_day_deducted_total(supabase, current_date)
    if deducted:
        st.success(f"今日彩色短袖库存已扣减 {deducted:,} 件。")
        return
    if st.button("读取今日生产并生成扣减表", key="colored_daily_load"):
        try:
            preview = build_colored_daily_preview(supabase, current_date)
            st.session_state[state_key] = preview
            st.session_state[date_key] = current_date
        except Exception as error:
            st.error(f"读取今日生产失败：{error}")
    preview = st.session_state.get(state_key)
    if preview is None or st.session_state.get(date_key) != current_date:
        return
    if preview.empty:
        st.info(f"{current_date:%m/%d} 暂无完整的彩色短袖生产数据")
        return
    st.dataframe(preview, hide_index=True, width="stretch")
    deferred = preview[preview["状态"] != "可扣减"]
    if not deferred.empty:
        st.warning(
            f"有 {int(deferred['未扣数量'].sum()):,} 件因库存为 0 或字段异常暂不扣减；"
            "生产消耗仍会进入模型，待清点后再处理库存差异。"
        )
    total = int(preview["预计扣减"].sum())
    st.caption(f"本次实际可扣减：{total:,} 件；库存最低扣到 0。")
    if not has_permission("can_edit_inventory"):
        st.info("当前账号只有查看权限，不能确认扣减库存。")
        return
    confirmed = st.checkbox(
        "我已核对生产数据和待清点差异",
        key="colored_daily_confirm",
    )
    if st.button(
        "确认扣减今日彩色短袖库存", type="primary",
        disabled=not confirmed, key="colored_daily_apply",
    ):
        try:
            imported = apply_colored_daily_deduction(
                supabase, preview, current_date, get_current_operator_name()
            )
            st.session_state.pop(state_key, None)
            st.session_state.pop(date_key, None)
            st.session_state["inventory_saved_message"] = (
                f"彩色短袖生产库存已扣减 {imported:,} 件"
            )
            st.rerun()
        except Exception as error:
            st.error(f"扣减失败：{error}")


def _stock_summary(inventory_df):
    if inventory_df is None or inventory_df.empty:
        return pd.DataFrame(columns=["颜色", "尺码", "当前库存"])
    frame = inventory_df.copy()
    frame["quantity"] = pd.to_numeric(frame["quantity"], errors="coerce").fillna(0)
    return (
        frame.groupby(["color", "size"], as_index=False)["quantity"].sum()
        .rename(columns={"color": "颜色", "size": "尺码", "quantity": "当前库存"})
    )
