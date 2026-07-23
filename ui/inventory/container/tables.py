import streamlit as st

from db.inventory import SIZE_COLUMNS
from db.inventory.container.packaging import build_container_packaging_summary
from db.inventory.container.tables import get_container_item_columns


def render_container_dataframe(display_df):
    table_df = display_df.drop(columns=["货柜记录ID"])
    item_columns = get_container_item_columns(display_df)
    column_config = {
        "发货日期": st.column_config.DateColumn("发货日期"),
        "运输天数": st.column_config.NumberColumn("运输天数", format="%d 天"),
        "预计到货日期": st.column_config.DateColumn("预计到货日期"),
        "实际到货日期": st.column_config.DateColumn("实际到货日期"),
        **{
            item: st.column_config.NumberColumn(
                _item_label(item), format="%d"
            )
            for item in item_columns
        },
        "总件数": st.column_config.NumberColumn("总件数", format="%d"),
    }
    if "成本" in table_df.columns:
        column_config["成本"] = st.column_config.NumberColumn(
            "成本", format="%.4f"
        )
    st.dataframe(
        table_df, hide_index=True, width="stretch",
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
    item_columns = get_container_item_columns(display_df)
    front = ["部门", "品类", "品牌", "材质", "颜色", "备注"]
    cost = ["成本"] if "成本" in detail_df.columns else []
    detail_df = detail_df[[*front, *cost, *item_columns, "总件数"]]
    config = {
        "备注": st.column_config.TextColumn("备注", width="large"),
        **{
            item: st.column_config.NumberColumn(
                _item_label(item), format="%d"
            )
            for item in item_columns
        },
        "总件数": st.column_config.NumberColumn("总件数", format="%d"),
    }
    if "成本" in detail_df.columns:
        config["成本"] = st.column_config.NumberColumn(
            "成本", format="%.4f"
        )
    st.dataframe(
        detail_df, hide_index=True, width="stretch", column_config=config
    )
    packaging_df = build_container_packaging_summary(display_df, container_key)
    render_packaging_check(packaging_df)


def render_packaging_check(packaging_df, title="箱装核对"):
    if packaging_df.empty:
        return
    st.subheader(title)
    has_mixed_packaging = any(
        str(value) == "混装"
        for size in SIZE_COLUMNS
        for value in packaging_df[size]
    )
    if has_mixed_packaging:
        packaging_records = [
            value for value in packaging_df["包装记录"].dropna().unique()
            if str(value).strip()
        ]
        if packaging_records:
            st.warning(
                "默认箱规无法整除，已优先读取备注中的包装记录："
                + "；".join(packaging_records)
            )
        else:
            st.warning("该货柜无法完全以箱数显示，备注中也没有包装记录。")
    st.dataframe(
        packaging_df,
        hide_index=True,
        width="stretch",
        column_config={
            "核对规格": st.column_config.TextColumn("核对规格", width="small"),
            "包装记录": st.column_config.TextColumn("包装记录", width="medium"),
            **{
                size: st.column_config.TextColumn(size, width="medium")
                for size in SIZE_COLUMNS
            },
            "总件数": st.column_config.NumberColumn("总件数", format="%d"),
            "备注": st.column_config.TextColumn("备注", width="large"),
        },
    )


def _item_label(value):
    return "yuan" if str(value).upper() == "YUAN" else value
