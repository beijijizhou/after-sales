import pandas as pd
import streamlit as st

from db.inventory.core.constants import SIZE_COLUMNS
from automation.sync.dtf_colored_inventory import (
    COLORED_MAPPING_RULE_VERSION,
    apply_colored_daily_deduction,
    build_colored_mapping_audit,
    build_colored_mapping_wide_table,
    build_colored_reconciliation_backlog,
    build_colored_consumption_wide_table,
    build_colored_daily_preview,
    load_colored_day_deducted_total,
    load_colored_consumption_history,
    list_colored_cached_dates,
)
from utils.auth.session import get_current_operator_name, has_permission
from ui.inventory.shared.filters import _reset_invalid_selectbox
from utils.sku_sorting import sort_sku_rows


def render_colored_consumption(supabase, current_date, inventory_df):
    view = st.segmented_control(
        "彩色短袖数据视图",
        ["日耗模型", "待核对差异"],
        default="日耗模型",
        key="colored_consumption_view",
    ) or "日耗模型"
    if view == "日耗模型":
        _render_colored_consumption_model(
            supabase, current_date, inventory_df
        )
    else:
        _render_colored_reconciliation(supabase, current_date)


def _render_colored_consumption_model(supabase, current_date, inventory_df):
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


def _render_colored_mapping_review(current_date):
    st.subheader("彩色短袖映射关系")
    st.caption(
        f"当前规则版本：{COLORED_MAPPING_RULE_VERSION}。这里只复查生产原始字段"
        "如何转换成统一口径，不读取当前库存、品牌、材质或库存数量。"
    )
    dates = list_colored_cached_dates(current_date, 14)
    if not dates:
        st.info("最近 14 天没有可复查的彩色短袖生产缓存。")
    else:
        _reset_invalid_selectbox("colored_mapping_audit_date", dates)
        selected_date = st.selectbox(
            "查看生产日期",
            dates,
            format_func=lambda value: value.strftime("%Y-%m-%d"),
            key="colored_mapping_audit_date",
        )
        try:
            source_map, metadata = build_colored_mapping_audit(selected_date)
        except Exception as error:
            st.error(f"彩色短袖映射关系加载失败：{error}")
        else:
            included = "、".join(
                metadata.get("included_platforms") or ()
            ) or "未记录"
            missing = "、".join(
                metadata.get("missing_platforms") or ()
            ) or "无"
            st.info(f"已读取平台：{included}｜尚未读取平台：{missing}")
            st.markdown("#### 生产字段标准化")
            st.caption(
                "颜色先按别名标准化（例如 golden → 黄色），浅灰再映射到库存灰色；"
                "尺码统一为 S–5XL 并横向汇总。颜色或尺码异常会明确显示，"
                "不会静默丢弃。实际扣减批次与 SKU 明细请在“库存流水”查看。"
            )
            if source_map.empty:
                st.info("所选日期没有彩色短袖映射数据。")
            else:
                mapping_wide = build_colored_mapping_wide_table(source_map)
                st.dataframe(
                    mapping_wide, hide_index=True, width="stretch",
                    column_config={
                        size: st.column_config.NumberColumn(
                            size, format="%d 件"
                        )
                        for size in [*SIZE_COLUMNS, "其他/异常"]
                    },
                )


def _render_colored_reconciliation(supabase, current_date):
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
    reconciliation_dates = backlog["日期"].tolist()
    backlog_by_date = backlog.set_index("日期").to_dict("index")
    _reset_invalid_selectbox(
        "colored_reconciliation_date", reconciliation_dates
    )
    selected_date = st.selectbox(
        "选择要处理的差异日期",
        reconciliation_dates,
        format_func=lambda value: (
            f"{value:%Y-%m-%d}｜{backlog_by_date[value]['状态']}｜"
            f"待核对 {int(backlog_by_date[value]['库存/SKU待核对']):,} 件"
        ),
        key="colored_reconciliation_date",
    )
    selected_summary = backlog_by_date[selected_date]
    st.info(
        f"该日生产 {int(selected_summary['生产数据']):,} 件，"
        f"已扣库存 {int(selected_summary['已扣库存']):,} 件，"
        f"当前可补扣 {int(selected_summary['当前可补扣']):,} 件，"
        f"仍待核对 {int(selected_summary['库存/SKU待核对']):,} 件。"
    )
    if selected_summary["尚未读取平台"] != "无":
        st.warning(
            f"尚未读取平台：{selected_summary['尚未读取平台']}。"
            "平台数据补齐后，生产总数和待处理数量可能继续变化。"
        )
        st.page_link(
            "pages/7_生产数据.py",
            label="打开生产数据，补齐缺失平台 →",
        )
    preview_key = "colored_reconciliation_preview"
    preview_date_key = "colored_reconciliation_preview_date"
    if st.button(
        "查看所选日期待处理明细",
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
    detail = sort_sku_rows(
        _stock_change_display(preview),
        material="材质", color="颜色", size="尺码",
        leading=["状态", "品牌"],
    )
    detail["核对方式"] = detail["状态"].map(_reconciliation_action)
    display_columns = [
        column for column in [
            "状态", "核对方式", "生产平台", "原始生产颜色",
            "原始生产尺码", "材质", "品牌", "颜色", "尺码",
            "当前库存", "本次出库 (-)", "调整后库存", "待处理数量",
        ]
        if column in detail.columns
    ]
    st.dataframe(
        detail[display_columns], hide_index=True, width="stretch",
        column_config={
            "核对方式": st.column_config.TextColumn(width="large"),
            "本次出库 (-)": st.column_config.NumberColumn(format="%d 件"),
            "待处理数量": st.column_config.NumberColumn(format="%d 件"),
        },
    )
    reason_summary = (
        detail.groupby("状态", dropna=False, as_index=False)
        .agg(
            当前可补扣=("本次出库 (-)", lambda values: int(values.abs().sum())),
            待处理数量=("待处理数量", "sum"),
        )
    )
    st.markdown("#### 待处理原因汇总")
    st.dataframe(reason_summary, hide_index=True, width="stretch")
    _render_reconciliation_steps(
        detail, selected_summary["尚未读取平台"]
    )
    quantity = int(
        detail["本次出库 (-)"].abs().sum()
        if "本次出库 (-)" in detail else 0
    )
    if quantity:
        st.info(
            f"当前可继续扣减 {quantity:,} 件。"
            "该操作只处理差额，不会重复扣除已出库数量。"
        )
    else:
        st.info(
            "该日期目前没有可继续扣减的库存；明细仍可复查，"
            "请按上方核对步骤处理后，再回来补扣。"
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
    view = st.segmented_control(
        "彩色短袖库存扣减视图",
        ["每日扣减", "生产字段映射"],
        default="每日扣减",
        key="colored_daily_deduction_view",
    ) or "每日扣减"
    if view == "生产字段映射":
        _render_colored_mapping_review(current_date)
        return
    _render_colored_daily_deduction_form(supabase, current_date)


def _render_colored_daily_deduction_form(supabase, current_date):
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
    st.dataframe(
        _stock_change_display(preview), hide_index=True, width="stretch"
    )
    deferred = preview[preview["状态"] != "可扣减"]
    if not deferred.empty:
        st.warning(
            f"有 {int(deferred['未扣数量'].sum()):,} 件因库存为 0 或字段异常暂不扣减；"
            "生产消耗仍会进入模型，待清点后再处理库存差异。"
        )
    total = int(pd.to_numeric(
        preview.loc[preview["状态"] == "可扣减", "预计扣减"],
        errors="coerce",
    ).fillna(0).sum())
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


def _stock_change_display(preview):
    display = pd.DataFrame(preview).rename(columns={
        "预计扣减": "本次出库 (-)",
        "扣减后库存": "调整后库存",
        "未扣数量": "待处理数量",
    })
    if "本次出库 (-)" in display:
        deductible = display.get(
            "状态", pd.Series("可扣减", index=display.index)
        ).eq("可扣减")
        quantities = pd.to_numeric(
            display["本次出库 (-)"], errors="coerce"
        ).fillna(0).abs().astype(int)
        display["本次出库 (-)"] = -quantities.where(deductible, 0)
    if "待处理数量" not in display:
        display["待处理数量"] = 0
    display["待处理数量"] = pd.to_numeric(
        display["待处理数量"], errors="coerce"
    ).fillna(0).astype(int)
    return display


def _reconciliation_action(status):
    status = str(status or "").strip()
    if status == "可扣减":
        return "核对三段式库存后，可直接补扣"
    if "库存为 0" in status:
        return "清点实物；有货先做临时库存调整，无货则保留待处理"
    if "映射" in status or "异常" in status:
        return "核对生产原始字段；确认颜色/尺码后修正规则或 SKU"
    return "查看生产原始字段与库存 SKU 后处理"


def _render_reconciliation_steps(detail, missing_platforms):
    st.markdown("#### 怎么核对")
    pending = pd.to_numeric(
        detail.get("待处理数量", 0), errors="coerce"
    ).fillna(0)
    statuses = detail.get(
        "状态", pd.Series("", index=detail.index)
    ).fillna("").astype(str)
    zero_stock = int(pending[statuses.str.contains("库存为 0")].sum())
    mapping = int(
        pending[statuses.str.contains("映射|异常", regex=True)].sum()
    )
    steps = []
    if zero_stock:
        steps.append({
            "问题": "账面库存为 0",
            "数量": zero_stock,
            "处理": (
                "清点对应颜色和尺码；有实货就在“临时库存调整”入库补到账，"
                "再返回本页补扣；确实无货则保留待处理。"
            ),
        })
    if mapping:
        steps.append({
            "问题": "生产字段未映射",
            "数量": mapping,
            "处理": (
                "按表内生产平台、原始颜色和原始尺码核对；"
                "到“系统库存扣减 → 生产字段映射”查看完整来源。"
            ),
        })
    if str(missing_platforms) != "无":
        steps.append({
            "问题": "生产平台尚未读取",
            "数量": None,
            "处理": f"到生产数据页补齐：{missing_platforms}。",
        })
    if not steps:
        steps.append({
            "问题": "可直接补扣",
            "数量": 0,
            "处理": "核对当前库存、本次出库和调整后库存，然后确认补扣。",
        })
    st.dataframe(
        pd.DataFrame(steps), hide_index=True, width="stretch",
        column_config={
            "数量": st.column_config.NumberColumn(format="%d 件"),
            "处理": st.column_config.TextColumn(width="large"),
        },
    )


def _stock_summary(inventory_df):
    if inventory_df is None or inventory_df.empty:
        return pd.DataFrame(columns=["颜色", "尺码", "当前库存"])
    frame = inventory_df.copy()
    frame["quantity"] = pd.to_numeric(frame["quantity"], errors="coerce").fillna(0)
    return (
        frame.groupby(["color", "size"], as_index=False)["quantity"].sum()
        .rename(columns={"color": "颜色", "size": "尺码", "quantity": "当前库存"})
    )
