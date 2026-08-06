import pandas as pd
import streamlit as st

from db.inventory.core.constants import SIZE_COLUMNS
from automation.sync.dtf_colored_inventory import (
    apply_colored_daily_deduction,
    build_colored_consumption_wide_table,
    build_colored_daily_preview,
    load_colored_day_deducted_total,
    load_colored_consumption_history,
)
from utils.auth.session import get_current_operator_name, has_permission


def render_colored_consumption(supabase, current_date, inventory_df):
    st.subheader("彩色短袖每日消耗")
    st.caption(
        "按最近 14 天的有效生产日计算；库存扣减请到“系统库存扣减”。"
    )
    history = load_colored_consumption_history(supabase, current_date, 14)
    if history.empty:
        st.info("最近 14 天暂无已同步的彩色短袖生产消耗")
        return
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
