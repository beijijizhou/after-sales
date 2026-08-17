import pandas as pd
import streamlit as st

from automation.sync.colored_period import (
    LOOKBACK_DAYS,
    build_colored_platform_status,
    load_colored_api_period_model,
    refresh_colored_api_period,
)
from utils.auth.session import get_current_operator_name
from ui.inventory.planning.colored_daily import (
    render_colored_daily_deduction_form,
)
from ui.inventory.planning.colored_review import (
    render_colored_mapping_review as _render_colored_mapping_review,
    render_colored_reconciliation as _render_colored_reconciliation,
)
from ui.inventory.planning.comparison import render_model_detail


def render_colored_consumption(
    supabase, current_date, inventory_df, visible_sizes=None,
):
    view = st.segmented_control(
        "彩色短袖数据视图",
        ["平台生产模型", "待核对差异"],
        default="平台生产模型",
        key="colored_consumption_view",
    ) or "平台生产模型"
    if view == "平台生产模型":
        _render_colored_consumption_model(
            supabase, current_date, inventory_df, visible_sizes
        )
    else:
        _render_colored_reconciliation(supabase, current_date)


def _render_colored_consumption_model(
    supabase, current_date, inventory_df, visible_sizes=None,
):
    st.subheader("彩色短袖消耗模型")
    st.caption(
        f"唯一数据来源为最近 {LOOKBACK_DAYS} 个完整自然日的各平台 "
        "ERP/API 生产数据。"
        "不同品牌属于调货来源，统一合并到相同颜色和尺码；仓库每日出库"
        "只作备份审计，不参与本模型。"
    )
    model = load_colored_api_period_model(current_date, supabase=supabase)
    if model.source == "database" and not model.data.empty:
        st.success(
            "已从数据库加载最近 30 天彩色短袖生产消耗模型；"
            "本地和部署环境共用这份数据，无需重新读取平台。"
        )
    elif model.source == "local_cache" and not model.data.empty:
        st.warning(
            "当前显示的是本机缓存。它不会自动同步到 Streamlit Cloud；"
            "请刷新一次并确认模型成功保存到数据库。"
        )
    with st.expander(
        (
            f"管理员：重新读取最近 {LOOKBACK_DAYS} 天平台数据"
            if not model.data.empty
            else f"如何读取最近 {LOOKBACK_DAYS} 天平台数据"
        ),
        expanded=model.data.empty,
    ):
        st.markdown(
            f"1. 点击下方 **并发读取并更新最近 {LOOKBACK_DAYS} 天平台数据**。\n"
            "2. 系统会按平台和 7 天区间并发读取；已有缓存会自动复用。\n"
            "3. 完成后查看平台状态表；系统会区分未开始、部分读取、"
            "登录过期、平台限制以及模型数据尚未保存。\n"
            "4. 个别平台失败不会清除其他平台已经读取的数据。"
        )
        if st.button(
            f"并发读取并更新最近 {LOOKBACK_DAYS} 天平台数据",
            key="refresh_colored_90_day_api_model",
        ):
            model = _refresh_colored_model(supabase, current_date)
    _render_colored_model_result(model, visible_sizes)


def _refresh_colored_model(supabase, current_date):
    progress = st.progress(0, text="准备读取各平台 API")

    def report(done, total, message):
        progress.progress(
            done / max(total, 1), text=f"{done}/{total}｜{message}"
        )

    try:
        model = refresh_colored_api_period(
            current_date, st.secrets, report_progress=report,
            supabase=supabase,
            operator=get_current_operator_name(),
        )
    except Exception as error:
        progress.empty()
        st.error(f"平台数据更新失败：{error}")
        return load_colored_api_period_model(
            current_date, supabase=supabase
        )
    progress.empty()
    st.success(f"最近 {LOOKBACK_DAYS} 天统一衣服生产数据已更新。")
    return model


def _render_colored_model_result(model, visible_sizes=None):
    st.subheader("平台读取状态")
    status = build_colored_platform_status(model)
    st.dataframe(status, hide_index=True, width="stretch")
    incomplete = status[~status["读取状态"].eq("已读取")]
    if model.storage_error:
        if model.source == "database" and not model.data.empty:
            st.warning(
                "生产消耗模型已从数据库加载，但平台覆盖审计暂时不可用；"
                "这不影响当前日耗和点货计算。"
            )
        else:
            st.error(
                "生产消耗模型数据库尚未就绪。请依次执行 "
                "sql/production/consumption/01_tables.sql 和 "
                "02_replace_rpc.sql；平台缓存仍可显示，不会因此当作凭据失败。"
            )
    if not incomplete.empty and model.source == "database":
        st.caption(
            "数据库模型已经可用于日耗和点货；平台完整度审计尚未覆盖："
            + "、".join(incomplete["平台"].astype(str))
            + "。需要更新模型时再使用上方管理员刷新入口。"
        )
    elif not incomplete.empty:
        st.warning(
            "尚未完整覆盖：" + "、".join(incomplete["平台"].astype(str))
            + "。请按表格中的“下一步”分别处理。"
        )
    if model.data.empty:
        st.info(
            f"数据库和本地缓存均没有最近 {LOOKBACK_DAYS} 天模型，"
            "请使用上方管理员入口读取。"
        )
        return
    display = model.data
    if visible_sizes:
        display = display[display["尺码"].isin(visible_sizes)]
    daily_total = pd.to_numeric(
        display["平台生产日均"], errors="coerce"
    ).fillna(0).sum()
    columns = st.columns(3)
    columns[0].metric("平台生产日均", f"{daily_total:,.1f} 件")
    columns[1].metric("统计范围", f"{LOOKBACK_DAYS} 天")
    columns[2].metric(
        "平台覆盖",
        f"完整 {len(model.included_platforms)} / 有数据 "
        f"{len(model.available_platforms)}",
    )
    st.caption(f"数据期间：{model.start_date} 至 {model.end_date}")
    render_model_detail(
        display, "平台生产日均", f"{LOOKBACK_DAYS}天平台API模型"
    )


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
    render_colored_daily_deduction_form(supabase, current_date)
