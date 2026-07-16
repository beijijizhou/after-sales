import streamlit as st

from db.inventory import SIZE_COLUMNS


def render_container_dataframe(display_df):
    table_df = display_df.drop(columns=["货柜记录ID"])
    column_config = {
        "发货日期": st.column_config.DateColumn("发货日期"),
        "运输天数": st.column_config.NumberColumn("运输天数", format="%d 天"),
        "预计到货日期": st.column_config.DateColumn("预计到货日期"),
        "实际到货日期": st.column_config.DateColumn("实际到货日期"),
        **{
            size: st.column_config.NumberColumn(size, format="%d")
            for size in SIZE_COLUMNS
        },
        "总件数": st.column_config.NumberColumn("总件数", format="%d"),
    }
    if "成本" in table_df.columns:
        column_config["成本"] = st.column_config.NumberColumn("成本", format="%.2f")
    st.dataframe(
        table_df, hide_index=True, use_container_width=True,
        column_config=column_config,
    )


def render_container_detail(display_df, container_key):
    detail_df = display_df[display_df["货柜记录ID"] == container_key].copy()
    if detail_df.empty:
        return
    container_no = detail_df["货柜号"].iloc[0] or detail_df["批次标识"].iloc[0]
    st.subheader(f"{container_no} 明细")
    hidden = [
        "货柜记录ID", "批次标识", "发货日期", "运输天数", "预计到货日期",
        "实际到货日期", "货柜号", "状态",
    ]
    detail_df = detail_df.drop(columns=hidden)
    config = {
        **{
            size: st.column_config.NumberColumn(size, format="%d")
            for size in SIZE_COLUMNS
        },
        "总件数": st.column_config.NumberColumn("总件数", format="%d"),
    }
    if "成本" in detail_df.columns:
        config["成本"] = st.column_config.NumberColumn("成本", format="%.2f")
    st.dataframe(
        detail_df, hide_index=True, use_container_width=True, column_config=config
    )
