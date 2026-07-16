import streamlit as st


def render_latest_platform_cards(latest_df, columns_per_row=3):
    st.subheader("各平台最新10个条码")
    if latest_df.empty:
        st.info("暂无最新条码")
        return

    platforms = latest_df["平台"].drop_duplicates().tolist()
    for start in range(0, len(platforms), columns_per_row):
        cols = st.columns(columns_per_row)
        for col, platform in zip(cols, platforms[start:start + columns_per_row]):
            platform_df = latest_df[latest_df["平台"] == platform]
            with col:
                render_platform_card(platform, platform_df)


def render_platform_card(platform, platform_df):
    last_time = platform_df.iloc[0]["扫描时间"] if not platform_df.empty else ""
    st.markdown(
        f"""
        <div class="platform-card-title-row">
            <strong>{platform}</strong>
            <span>最后 {last_time}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    display_df = build_display_df(platform_df)
    st.dataframe(
        display_df,
        hide_index=True,
        width="stretch",
        height=318,
        column_config={
            "扫描时间": st.column_config.TextColumn("时间", width="small"),
            "质检人员": st.column_config.TextColumn("质检", width="small"),
            "条码": st.column_config.TextColumn("条码", width="large"),
        },
    )


def build_display_df(platform_df):
    display_df = platform_df[["扫描时间", "质检人员", "条码"]].copy()
    display_df["条码"] = display_df["条码"].astype(str).apply(truncate_barcode)
    return display_df


def truncate_barcode(barcode, max_length=18):
    barcode = str(barcode)
    if len(barcode) <= max_length:
        return barcode
    return f"{barcode[:10]}...{barcode[-5:]}"


st.markdown(
    """
    <style>
    .platform-card-title-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 10px;
        padding: 8px 10px;
        margin-top: 4px;
        border: 1px solid #E5E7EB;
        border-bottom: 0;
        border-radius: 8px 8px 0 0;
        background: #F8FAFC;
    }
    .platform-card-title-row strong {
        color: #111827;
        font-size: 15px;
    }
    .platform-card-title-row span {
        color: #64748B;
        font-size: 12px;
        white-space: nowrap;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
