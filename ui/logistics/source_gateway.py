"""Replaceable ERP source adapters for logistics synchronization."""

import streamlit as st

from automation.logistics import (
    S2BAuthenticationError,
    fetch_diy19_shipments,
    fetch_s2b_pending_shipments,
    fetch_sds_pending_shipments,
    load_diy19_logistics_credentials,
    load_s2b_account,
    load_sds_account,
    local_login_available,
    refresh_local_s2b_token,
)
from automation.logistics.humbird import (
    HUMBIRD_OPEN_LOGISTICS_PLATFORMS,
    fetch_humbird_shipments,
)
from automation.production import SDS_PLATFORM_PROFILES
from automation.api.humbird.config import load_humbird_credentials
from db.supabase_client import supabase
from ui.logistics.review.model import erp_time_range


def fetch_source(source, department, status, start_date, end_date):
    if source in HUMBIRD_OPEN_LOGISTICS_PLATFORMS:
        return fetch_humbird_shipments(
            source,
            load_humbird_credentials(st.secrets, source, supabase),
            start_date,
            end_date,
            status=status,
            department=department,
        )
    if source in {"七创", "一朵云"}:
        return fetch_diy19_shipments(
            source, load_diy19_logistics_credentials(st.secrets, source),
            start_date, end_date, stage=status,
        )
    if source in SDS_PLATFORM_PROFILES:
        profile = SDS_PLATFORM_PROFILES[source]
        return fetch_sds_pending_shipments(
            profile, load_sds_account(st.secrets, profile), 100,
            status=status, time_range=erp_time_range(start_date, end_date),
            platform_name=source, department=department,
        )
    if source != "S2B":
        raise ValueError(f"{source} 已存在于生产数据平台目录，但尚未接入订单物流接口")
    account = department if department in {"UV", "3D"} else "DTF"
    try:
        return fetch_s2b_pending_shipments(
            account, _s2b_credentials(account), status=status
        )
    except S2BAuthenticationError:
        return fetch_s2b_pending_shipments(
            account, {"token": refresh_s2b_session(account)}, status=status
        )


def render_s2b_connection_status(selected):
    if "S2B" not in selected:
        return
    if local_login_available():
        st.caption(
            "本地模式：首次登录后会复用专用Chrome会话并直接调用API；"
            "只有登录状态失效时才需要重新登录或滑块验证。"
        )
    else:
        st.caption("云端模式：S2B账号由服务器Secrets或本地连接器提供。")


def _s2b_credentials(account):
    token = st.session_state.get("logistics_s2b_tokens", {}).get(account)
    if token:
        return {"token": token}
    try:
        return load_s2b_account(st.secrets, account)
    except ValueError:
        if not local_login_available():
            raise
        return {"token": refresh_s2b_session(account)}


def refresh_s2b_session(account):
    token = refresh_local_s2b_token(account)
    tokens = dict(st.session_state.get("logistics_s2b_tokens", {}))
    tokens[account] = token
    st.session_state["logistics_s2b_tokens"] = tokens
    return token
