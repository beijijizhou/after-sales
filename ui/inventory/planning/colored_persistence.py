import streamlit as st

from automation.sync.colored_period import (
    load_colored_api_period_model,
    persist_cached_colored_api_period,
)
from utils.auth.session import get_current_operator_name
from ui.inventory.planning.colored_model_source import (
    clear_colored_model_cache,
)


def render_cached_model_persistence(supabase, current_date, model):
    st.warning(
        "当前显示的是本机缓存。它不会自动同步到 Streamlit Cloud；"
        "可直接把这份缓存保存到共享数据库，不需要重新读取平台。"
    )
    st.caption(
        f"待发布期间：{model.start_date} 至 {model.end_date}｜"
        f"已有数据平台：{len(model.available_platforms)} 个。"
        "此操作只保存生产消耗模型，不会扣减库存。"
    )
    if not st.button(
        "将当前本地30天模型保存到共享数据库",
        type="primary",
        key="persist_cached_colored_period_model",
    ):
        return model
    try:
        result = persist_cached_colored_api_period(
            current_date,
            supabase,
            operator=get_current_operator_name(),
        )
    except Exception as error:
        st.error(f"本地模型保存失败：{error}")
    else:
        _render_persistence_result(result)
        clear_colored_model_cache()
    return load_colored_api_period_model(
        current_date, supabase=supabase
    )


def _render_persistence_result(result):
    if result.errors:
        st.error(
            f"已保存 {len(result.saved_platforms)} 个平台；"
            f"失败 {len(result.errors)} 个："
            + "；".join(
                f"{platform}：{message}"
                for platform, message in result.errors.items()
            )
        )
        return
    st.success(
        f"已将 {result.source_rows:,} 条本地彩色短袖生产记录按 "
        f"{len(result.saved_platforms)} 个平台保存到共享数据库；"
        "未重新请求 ERP，未扣减库存。"
    )
