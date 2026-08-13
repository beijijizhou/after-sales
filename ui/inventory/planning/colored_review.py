"""Colored-shirt mapping and reconciliation review views."""

import pandas as pd
import streamlit as st

from automation.sync.dtf_colored_inventory import (
    COLORED_MAPPING_RULE_VERSION,
    apply_colored_daily_deduction,
    build_colored_daily_preview,
    build_colored_mapping_audit,
    build_colored_mapping_wide_table,
    build_colored_reconciliation_backlog,
    list_colored_cached_dates,
)
from db.inventory.core.constants import SIZE_COLUMNS
from ui.inventory.shared.filters import _reset_invalid_selectbox
from ui.inventory.operations.system_deduction import system_deduction_display
from utils.auth.session import get_current_operator_name, has_permission
from utils.sku_sorting import sort_sku_rows


def render_colored_mapping_review(current_date):
    st.subheader("彩色短袖映射关系")
    st.caption(
        f"当前规则版本：{COLORED_MAPPING_RULE_VERSION}。这里只复查生产原始字段"
        "如何转换成统一口径，不读取库存数量。"
    )
    dates = list_colored_cached_dates(current_date, 14)
    if not dates:
        st.info("最近 14 天没有可复查的彩色短袖生产缓存。")
        return
    _reset_invalid_selectbox("colored_mapping_audit_date", dates)
    selected_date = st.selectbox(
        "查看生产日期", dates, format_func=lambda value: value.strftime("%Y-%m-%d"),
        key="colored_mapping_audit_date",
    )
    try:
        source_map, metadata = build_colored_mapping_audit(selected_date)
    except Exception as error:
        st.error(f"彩色短袖映射关系加载失败：{error}")
        return
    included = "、".join(metadata.get("included_platforms") or ()) or "未记录"
    missing = "、".join(metadata.get("missing_platforms") or ()) or "无"
    st.info(f"已读取平台：{included}｜尚未读取平台：{missing}")
    st.markdown("#### 生产字段标准化")
    st.caption(
        "颜色先按别名标准化，浅灰再映射到库存灰色；尺码统一为 S–5XL。"
        "异常会明确显示，不会静默丢弃。"
    )
    if source_map.empty:
        st.info("所选日期没有彩色短袖映射数据。")
        return
    mapping = build_colored_mapping_wide_table(source_map)
    st.dataframe(
        mapping, hide_index=True, width="stretch",
        column_config={
            size: st.column_config.NumberColumn(size, format="%d 件")
            for size in [*SIZE_COLUMNS, "其他/异常"]
        },
    )


def render_colored_reconciliation(supabase, current_date):
    st.subheader("彩色短袖待核对差异")
    st.caption("每日快速出库只执行一次；库存不足、SKU 未匹配单独处理。")
    try:
        backlog = build_colored_reconciliation_backlog(supabase, current_date, 14)
    except Exception as error:
        st.error(f"彩色短袖待核对差异加载失败：{error}")
        return
    if backlog.empty:
        st.success("最近 14 天没有已出库但尚待核对的彩色短袖差异。")
        return
    st.dataframe(backlog, hide_index=True, width="stretch")
    dates = backlog["日期"].tolist()
    by_date = backlog.set_index("日期").to_dict("index")
    _reset_invalid_selectbox("colored_reconciliation_date", dates)
    selected_date = st.selectbox(
        "选择要处理的差异日期", dates,
        format_func=lambda value: (
            f"{value:%Y-%m-%d}｜{by_date[value]['状态']}｜"
            f"待核对 {int(by_date[value]['库存/SKU待核对']):,} 件"
        ), key="colored_reconciliation_date",
    )
    selected = by_date[selected_date]
    st.info(
        f"该日生产 {int(selected['生产数据']):,} 件，"
        f"已扣 {int(selected['已扣库存']):,} 件，"
        f"当前可补扣 {int(selected['当前可补扣']):,} 件。"
    )
    if selected["尚未读取平台"] != "无":
        st.warning(f"尚未读取平台：{selected['尚未读取平台']}。")
        st.page_link("pages/7_生产数据.py", label="打开生产数据，补齐缺失平台 →")
    preview_key = "colored_reconciliation_preview"
    date_key = "colored_reconciliation_preview_date"
    if st.button("查看所选日期待处理明细", key="colored_reconciliation_preview_button"):
        st.session_state[preview_key] = build_colored_daily_preview(
            supabase, selected_date
        )
        st.session_state[date_key] = selected_date
    preview = st.session_state.get(preview_key)
    if preview is None or st.session_state.get(date_key) != selected_date:
        return
    detail = sort_sku_rows(
        stock_change_display(preview), material="材质", color="颜色", size="尺码",
        leading=["状态", "品牌"],
    )
    detail["核对方式"] = detail["状态"].map(reconciliation_action)
    columns = [column for column in [
        "状态", "核对方式", "生产平台", "原始生产颜色", "原始生产尺码",
        "材质", "品牌", "颜色", "尺码", "当前库存", "本次出库 (-)",
        "调整后库存", "待处理数量",
    ] if column in detail]
    st.dataframe(detail[columns], hide_index=True, width="stretch")
    render_reconciliation_steps(detail, selected["尚未读取平台"])
    quantity = int(detail.get("本次出库 (-)", pd.Series(dtype=int)).abs().sum())
    st.info(
        f"当前可继续扣减 {quantity:,} 件。该操作只处理差额。"
        if quantity else "目前没有可继续扣减的库存，请先按核对步骤处理。"
    )
    if not has_permission("can_edit_inventory"):
        st.info("当前账号只有查看权限，不能处理库存差额。")
        return
    confirmed = st.checkbox("我已核对所选日期的库存差额", key="colored_reconciliation_confirm")
    if not st.button(
        "确认补扣所选差额", type="primary", disabled=not confirmed or quantity <= 0,
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
    st.session_state.pop(date_key, None)
    st.session_state["inventory_saved_message"] = (
        f"{selected_date:%m/%d} 彩色短袖差额已补扣 {imported:,} 件"
    )
    st.rerun()


def stock_change_display(preview):
    return system_deduction_display(
        preview, eligible_status="可扣减", pending_column="未扣数量"
    )


def reconciliation_action(status):
    status = str(status or "").strip()
    if status == "可扣减":
        return "核对三段式库存后，可直接补扣"
    if "库存为 0" in status:
        return "清点实物；有货先做临时库存调整，无货则保留待处理"
    if "映射" in status or "异常" in status:
        return "核对生产原始字段；确认颜色/尺码后修正规则或 SKU"
    return "查看生产原始字段与库存 SKU 后处理"


def render_reconciliation_steps(detail, missing_platforms):
    st.markdown("#### 怎么核对")
    pending = pd.to_numeric(detail.get("待处理数量", 0), errors="coerce").fillna(0)
    statuses = detail.get("状态", pd.Series("", index=detail.index)).fillna("").astype(str)
    zero_stock = int(pending[statuses.str.contains("库存为 0")].sum())
    mapping = int(pending[statuses.str.contains("映射|异常", regex=True)].sum())
    steps = []
    if zero_stock:
        steps.append({"问题": "账面库存为 0", "数量": zero_stock,
                      "处理": "清点实物；有货先临时入库，再返回补扣。"})
    if mapping:
        steps.append({"问题": "生产字段未映射", "数量": mapping,
                      "处理": "按生产平台、原始颜色和原始尺码核对映射。"})
    if str(missing_platforms) != "无":
        steps.append({"问题": "生产平台尚未读取", "数量": None,
                      "处理": f"到生产数据页补齐：{missing_platforms}。"})
    if not steps:
        steps.append({"问题": "可直接补扣", "数量": 0,
                      "处理": "核对当前库存、本次出库和调整后库存。"})
    st.dataframe(pd.DataFrame(steps), hide_index=True, width="stretch")
