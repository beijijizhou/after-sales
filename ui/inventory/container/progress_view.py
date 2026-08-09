import streamlit as st


def render_arrival_alerts(progress_df):
    delayed = progress_df[progress_df["剩余天数"] < 0]
    arriving = progress_df[
        progress_df["剩余天数"].between(0, 7, inclusive="both")
    ]
    if not delayed.empty:
        labels = "；".join(
            f"{row['货柜备注']}（已延迟{abs(int(row['剩余天数']))}天）"
            for _, row in delayed.iterrows()
        )
        st.error(f"延迟到柜提醒：{labels}")
    if not arriving.empty:
        labels = "；".join(
            f"{row['货柜备注']}（{int(row['剩余天数'])}天）"
            for _, row in arriving.iterrows()
        )
        st.warning(f"一周内到柜提醒：{labels}")
