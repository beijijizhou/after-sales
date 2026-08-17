from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from ui.daily_work.records import render_daily_record, render_history
from ui.daily_work.settings import render_task_settings
from utils.auth import get_current_user


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_daily_work_page(supabase):
    user = get_current_user() or {}
    owner = str(user.get("username") or "").strip()
    display_name = str(user.get("display_name") or owner).strip()
    if not owner:
        st.error("无法识别当前登录账号")
        return
    message = st.session_state.pop("daily_work_saved_message", None)
    if message:
        st.success(message)
    st.title("每日工作")
    st.caption(f"{display_name} 的个人工作记录 · 按纽约日期保存")
    today = datetime.now(NY_TIMEZONE).date()
    record_tab, history_tab, settings_tab = st.tabs([
        "当天记录", "历史记录", "任务设置",
    ])
    with record_tab:
        render_daily_record(supabase, owner, display_name, today)
    with history_tab:
        render_history(supabase, owner, today)
    with settings_tab:
        render_task_settings(supabase, owner, display_name)
