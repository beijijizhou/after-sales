from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.logistics.usps_usage import (
    load_latest_usps_usage_baseline,
    load_usps_usage_events,
    save_usps_usage_baseline,
)
from utils.auth import has_permission
from utils.auth import get_current_operator_name


NEW_YORK = ZoneInfo("America/New_York")


def render_usps_usage(supabase, database_error):
    now = datetime.now(NEW_YORK)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    try:
        events = load_usps_usage_events(supabase, month_start)
        baseline = load_latest_usps_usage_baseline(supabase, month_start)
    except Exception as error:
        message = database_error(error)
        st.warning(
            message if "02_usps_usage.sql" in message
            else "USPS用量统计暂时不可用，请稍后重试。"
        )
        return
    monthly_limit = int(st.secrets.get("USPS_MONTHLY_LIMIT") or 100000)
    summary, daily = summarize_usps_usage(
        events, baseline, now, monthly_limit
    )
    st.subheader("USPS API用量")
    metrics = st.columns(4)
    metrics[0].metric("今日查询", f"{summary['today']:,}")
    metrics[1].metric("本月已用", f"{summary['month_used']:,}")
    metrics[2].metric("本月剩余", f"{summary['remaining']:,}")
    metrics[3].metric("API批次", f"{summary['request_count']:,}")
    st.progress(min(1.0, summary["month_used"] / max(1, monthly_limit)))
    st.caption(
        f"月额度 {monthly_limit:,}｜已使用 {summary['percent']:.2f}%｜"
        "追踪号用量按实际提交给USPS的物流单号数量统计。"
    )
    if baseline:
        st.caption(
            f"官方后台校准值 {int(baseline.get('official_count') or 0):,}｜"
            f"校准时间 {_ny_timestamp(baseline.get('created_at'))}"
        )
    with st.expander("每日USPS查询明细"):
        if daily.empty:
            st.info("本月还没有系统查询记录。")
        else:
            st.dataframe(daily, hide_index=True, width="stretch")
    with st.expander("校准官方后台用量"):
        st.caption(
            "USPS后台当前显示408时，在这里填写408并保存一次；"
            "之后系统会在该基准上继续累计。"
        )
        official_count = st.number_input(
            "官方本月已用量",
            min_value=0,
            max_value=monthly_limit,
            value=int(baseline.get("official_count") or 0) if baseline else 0,
            step=1,
            key="logistics_usps_official_usage",
        )
        if st.button("保存官方用量校准", width="stretch"):
            if not has_permission("can_manage_logistics"):
                st.error("当前账号没有校准USPS用量的权限。")
            else:
                save_usps_usage_baseline(
                    supabase, official_count, get_current_operator_name()
                )
                st.success("官方用量基准已保存。")
                st.rerun()


def summarize_usps_usage(events, baseline, now, monthly_limit):
    frame = events.copy() if events is not None else pd.DataFrame()
    if frame.empty:
        frame = pd.DataFrame(columns=[
            "event_type", "tracking_count", "request_count", "created_at"
        ])
    frame["created_at"] = pd.to_datetime(
        frame.get("created_at"), errors="coerce", utc=True
    )
    frame["tracking_count"] = pd.to_numeric(
        frame.get("tracking_count"), errors="coerce"
    ).fillna(0).astype(int)
    frame["request_count"] = pd.to_numeric(
        frame.get("request_count"), errors="coerce"
    ).fillna(0).astype(int)
    queries = frame[frame.get("event_type", "query") == "query"].copy()
    queries["纽约日期"] = queries["created_at"].dt.tz_convert(NEW_YORK).dt.date
    today = int(queries.loc[
        queries["纽约日期"] == now.date(), "tracking_count"
    ].sum())
    baseline_count = int((baseline or {}).get("official_count") or 0)
    if baseline and baseline.get("created_at"):
        baseline_time = pd.to_datetime(baseline["created_at"], utc=True)
        counted_queries = queries[queries["created_at"] > baseline_time]
    else:
        counted_queries = queries
    month_used = baseline_count + int(counted_queries["tracking_count"].sum())
    request_count = int(queries["request_count"].sum())
    daily = (
        queries.groupby("纽约日期", as_index=False)
        .agg(查询面单数=("tracking_count", "sum"), API批次=("request_count", "sum"))
        .rename(columns={"纽约日期": "日期"})
        .sort_values("日期", ascending=False)
    )
    return {
        "today": today,
        "month_used": month_used,
        "remaining": max(0, monthly_limit - month_used),
        "request_count": request_count,
        "percent": month_used / max(1, monthly_limit) * 100,
    }, daily


def _ny_timestamp(value):
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return "未知"
    return parsed.tz_convert(NEW_YORK).strftime("%Y-%m-%d %H:%M:%S（纽约）")
