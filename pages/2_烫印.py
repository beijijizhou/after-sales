from datetime import datetime, time
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

from db.supabase_client import supabase
from utils.utility import get_selected_date


st.title("烫印")

selected_date = get_selected_date()
st.caption(f"统计日期：{selected_date.isoformat()}")

start_at = datetime.combine(
    selected_date,
    time.min,
    tzinfo=ZoneInfo("America/New_York")
).isoformat()
end_at = datetime.combine(
    selected_date,
    time.max,
    tzinfo=ZoneInfo("America/New_York")
).isoformat()

try:
    rows = []
    page_size = 1000
    offset = 0

    while True:
        response = (
            supabase
            .table("barcode_scans")
            .select("hotstamp_by,scanned_at")
            .gte("scanned_at", start_at)
            .lte("scanned_at", end_at)
            .range(offset, offset + page_size - 1)
            .execute()
        )

        rows.extend(response.data)

        if len(response.data) < page_size:
            break

        offset += page_size

    df = pd.DataFrame(rows)
    if df.empty or "hotstamp_by" not in df.columns:
        st.warning("未找到数据")
        st.stop()

    df = (
        df
        .dropna(subset=["hotstamp_by"])
        .assign(hotstamp_by=lambda data: data["hotstamp_by"].astype(str).str.strip())
    )
    df = df[df["hotstamp_by"] != ""]

    if df.empty:
        st.warning("未找到数据")
        st.stop()

    df = (
        df
        .groupby("hotstamp_by", as_index=False)
        .size()
        .rename(columns={
            "hotstamp_by": "name",
            "size": "scan_count",
        })
        .sort_values("scan_count", ascending=False)
        .reset_index(drop=True)
    )

    st.metric(
        "总扫描数量",
        df["scan_count"].sum()
    )

    st.dataframe(df)

except Exception as e:
    st.error(
        f"数据加载失败：{e}"
    )
