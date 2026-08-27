import streamlit as st

from automation.production import DTF_PRODUCTION_PLATFORMS
from automation.sync.colored_period import (
    LOOKBACK_DAYS,
    load_colored_api_period_model,
    refresh_colored_api_period,
)
from utils.auth.session import get_current_operator_name


@st.cache_data(ttl=60, show_spinner=False)
def load_colored_model(_supabase, current_date):
    return load_colored_api_period_model(
        current_date, supabase=_supabase
    )


def clear_colored_model_cache():
    load_colored_model.clear()


def default_refresh_platforms(status):
    pending_states = {
        "未开始", "读取失败", "部分读取", "已读取｜日期待核对",
    }
    pending = set(status.loc[
        status["读取状态"].isin(pending_states), "平台"
    ].astype(str))
    return [
        platform for platform in DTF_PRODUCTION_PLATFORMS
        if platform in pending
    ]


def refresh_colored_model(supabase, current_date, platforms):
    selected = tuple(platforms)
    progress = st.progress(
        0, text="准备读取：" + "、".join(selected)
    )

    def report(done, total, message):
        progress.progress(
            done / max(total, 1), text=f"{done}/{total}｜{message}"
        )

    try:
        model = refresh_colored_api_period(
            current_date, st.secrets, report_progress=report,
            supabase=supabase,
            operator=get_current_operator_name(),
            platforms=selected,
        )
    except Exception as error:
        progress.empty()
        st.error(f"平台数据更新失败：{error}")
        return load_colored_api_period_model(
            current_date, supabase=supabase
        )
    progress.empty()
    clear_colored_model_cache()
    st.success(
        f"已更新最近 {LOOKBACK_DAYS} 天：" + "、".join(selected)
    )
    return model
