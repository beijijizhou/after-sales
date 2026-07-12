import json
from html import escape

import streamlit as st
import streamlit.components.v1 as components


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
    rows_html = "\n".join(
        build_barcode_row(row["扫描时间"], row["条码"])
        for row in platform_df.to_dict("records")
    )
    components.html(
        f"""
        <div class="platform-card">
            <div class="platform-card-header">
                <span class="platform-card-title">{escape(str(platform))}</span>
                <span class="platform-card-time">最后 {escape(str(last_time))}</span>
            </div>
            {rows_html}
        </div>
        {CARD_STYLE}
        """,
        height=330,
    )


def build_barcode_row(scan_time, barcode):
    barcode_text = str(barcode)
    button_payload = json.dumps(barcode_text)
    return f"""
    <div class="platform-barcode-row">
        <span class="platform-barcode-time">{escape(str(scan_time))}</span>
        <span class="platform-barcode-value">{escape(barcode_text)}</span>
        <button class="copy-button" onclick='navigator.clipboard.writeText({button_payload}); this.innerText="已复制"; setTimeout(() => this.innerText="复制", 900);'>
            复制
        </button>
    </div>
    """


CARD_STYLE = """
<style>
body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.platform-card {
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 12px 14px;
    min-height: 300px;
    background: #FFFFFF;
    box-sizing: border-box;
}
.platform-card-header {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: baseline;
    padding-bottom: 8px;
    margin-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
}
.platform-card-title {
    font-size: 16px;
    font-weight: 700;
    color: #111827;
}
.platform-card-time {
    font-size: 12px;
    color: #64748B;
    white-space: nowrap;
}
.platform-barcode-row {
    display: grid;
    grid-template-columns: 62px minmax(0, 1fr) 44px;
    gap: 8px;
    align-items: center;
    padding: 4px 0;
    font-size: 13px;
    border-bottom: 1px solid #F8FAFC;
}
.platform-barcode-time {
    color: #64748B;
    font-variant-numeric: tabular-nums;
}
.platform-barcode-value {
    color: #111827;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    overflow-wrap: anywhere;
}
.copy-button {
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    background: #F8FAFC;
    color: #334155;
    cursor: pointer;
    font-size: 12px;
    height: 24px;
}
.copy-button:hover {
    background: #EEF2FF;
    border-color: #94A3B8;
}
</style>
"""
