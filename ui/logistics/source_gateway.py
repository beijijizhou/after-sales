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
from automation.api.humbird import (
    HumbirdBrowserRefreshRequired,
    HUMBIRD_OPEN_LOGISTICS_PLATFORMS,
    fetch_humbird_shipments_legacy,
    fetch_humbird_shipments_with_fallback,
)
from automation.api.humbird.local_auth import (
    HumbirdLocalLoginRequired,
    local_humbird_login_available,
    refresh_local_humbird_token,
)
from automation.production import SDS_PLATFORM_PROFILES
from automation.api.humbird.config import load_humbird_credentials
from db.supabase_client import supabase
from ui.logistics.review.model import erp_time_range
from utils.auth import get_current_user


def fetch_source(
    source, department, status, start_date, end_date, report_progress=None,
):
    if source in HUMBIRD_OPEN_LOGISTICS_PLATFORMS:
        progress_options = (
            {"report_progress": report_progress} if report_progress else {}
        )
        credentials = load_humbird_credentials(
            st.secrets, source, supabase
        )
        credentials = _database_token_only(credentials)
        try:
            return fetch_humbird_shipments_with_fallback(
                source, credentials, start_date, end_date,
                status=status, department=department, **progress_options,
            )
        except HumbirdBrowserRefreshRequired as error:
            report = report_progress or (lambda _message: None)
            report(
                f"第2级数据库 token 不可用（{error}）；"
                "第3级：准备启动本地专用 Chrome。"
            )
            if not local_humbird_login_available():
                raise HumbirdLocalLoginRequired(
                    f"{source} 共享 token 已失效；当前云端不能启动浏览器，"
                    "请管理员在本地打开本系统并同步一次以更新数据库授权"
                ) from error
            refresh_local_humbird_token(
                source,
                st.secrets,
                supabase=supabase,
                updated_by=str(
                    (get_current_user() or {}).get("username") or "admin"
                ),
                report_progress=report_progress,
            )
            report("新 token 已加密写入数据库，正在重新请求备用 API。")
            refreshed = load_humbird_credentials(
                st.secrets, source, supabase
            )
            refreshed = _database_token_only(refreshed)
            refreshed["token_just_captured"] = True
            return fetch_humbird_shipments_legacy(
                source, refreshed, start_date, end_date,
                status=status, department=department, **progress_options,
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
            account,
            _s2b_credentials(account),
            status=status,
            start_date=start_date,
            end_date=end_date,
            report_progress=report_progress,
        )
    except S2BAuthenticationError:
        return fetch_s2b_pending_shipments(
            account,
            {"token": refresh_s2b_session(account)},
            status=status,
            start_date=start_date,
            end_date=end_date,
            report_progress=report_progress,
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


def _database_token_only(credentials):
    """Keep the official key but accept only the shared database fallback."""
    result = dict(credentials or {})
    source = (
        result.get("fallback_credential_source")
        if result.get("api_key")
        else result.get("credential_source")
    )
    if source != "database":
        result.pop("token", None)
    return result


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
