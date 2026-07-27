import streamlit as st


def render_data_status(start_date, end_date, source):
    saved_at = str(source.get("saved_at") or "").strip()
    source_name = str(source.get("file") or "").strip()
    is_cached_read = source_name.startswith("本地缓存")

    with st.container(border=True):
        range_col, fetched_col, source_col = st.columns([1.25, 1, 0.8])
        range_col.metric(
            "生产数据范围",
            f"{start_date:%Y-%m-%d} 至 {end_date:%Y-%m-%d}",
        )
        fetched_col.metric(
            "最近获取时间（纽约）",
            saved_at or "未记录",
        )
        source_col.metric(
            "当前来源",
            "本地缓存" if is_cached_read else "本次获取",
        )

        if saved_at:
            st.caption(
                "这份数据已保存在本地，可直接继续分析；"
                "只有需要更新日期范围或获取最新数据时才需重新获取。"
            )
        else:
            st.warning("这份数据尚未记录缓存时间，建议重新获取一次。")
