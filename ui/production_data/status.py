import streamlit as st


def build_platform_read_status(source, expected_platforms):
    metadata = dict(source.get("metadata") or {})
    data = source.get("data")
    included = set(metadata.get("included_platforms") or [])
    if not included and data is not None and "运营商" in data.columns:
        included = set(
            data["运营商"].dropna().astype(str).str.strip()
        )
    declared_missing = set(metadata.get("missing_platforms") or [])
    expected = list(expected_platforms)
    missing = declared_missing | (set(expected) - included)
    errors = {
        str(name): str(message)
        for name, message in (metadata.get("platform_errors") or {}).items()
    }
    rows = []
    for platform in expected:
        if platform in missing:
            reason = errors.get(platform) or (
                "历史缓存未记录失败原因，请点击获取生产数据重新读取缺失平台"
            )
            rows.append({
                "平台": platform, "读取状态": "未读取", "说明": reason,
            })
        else:
            rows.append({
                "平台": platform, "读取状态": "已读取", "说明": "—",
            })
    return rows


def render_data_status(
    start_date, end_date, source, expected_platforms=None,
):
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

    if expected_platforms:
        platform_rows = build_platform_read_status(
            source, expected_platforms
        )
        missing = [
            row for row in platform_rows if row["读取状态"] == "未读取"
        ]
        st.markdown("#### 平台读取情况")
        if missing:
            st.warning(
                "未读取平台：" + "、".join(
                    row["平台"] for row in missing
                )
            )
        else:
            st.success("所有配置平台均已读取。")
        st.dataframe(
            platform_rows,
            hide_index=True,
            width="stretch",
            column_config={
                "平台": st.column_config.TextColumn("平台", width="small"),
                "读取状态": st.column_config.TextColumn(
                    "读取状态", width="small"
                ),
                "说明": st.column_config.TextColumn("失败原因", width="large"),
            },
        )
