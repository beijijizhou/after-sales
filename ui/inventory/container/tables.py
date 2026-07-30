import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS
from db.inventory.container.packaging import build_container_packaging_summary
from db.inventory.container.tables import (
    build_container_display,
    build_container_inventory_summary,
    get_container_item_columns,
)


def render_container_records(raw_df, include_cost=False):
    if raw_df.empty:
        return
    departments = (
        raw_df["department"].fillna("").astype(str).str.strip()
        if "department" in raw_df.columns
        else None
    )
    if departments is None or departments.nunique() <= 1:
        render_container_dataframe(
            build_container_display(raw_df, include_cost)
        )
        return
    for department in departments.drop_duplicates():
        label = department or "未分类部门"
        st.markdown(f"**{label}**")
        department_df = raw_df[departments == department]
        render_container_dataframe(
            build_container_display(department_df, include_cost)
        )


def render_container_dataframe(display_df):
    table_df = display_df.drop(columns=["货柜记录ID"])
    if "型号" in table_df.columns:
        table_df = table_df.drop(columns=["总件数"])
    item_columns = get_container_item_columns(display_df)
    column_config = {
        "发货日期": st.column_config.DateColumn("发货日期"),
        "运输天数": st.column_config.NumberColumn("运输天数", format="%d 天"),
        "预计到货日期": st.column_config.DateColumn("预计到货日期"),
        "实际到货日期": st.column_config.DateColumn("实际到货日期"),
        "实际到货时间（纽约）": st.column_config.TextColumn(
            "实际到货时间（纽约）"
        ),
        "型号": st.column_config.TextColumn("型号"),
        "数量": st.column_config.NumberColumn("数量", format="%d"),
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


def render_container_inventory_summary(raw_df, title):
    if raw_df.empty:
        return
    st.subheader(title)
    st.caption(
        "已合并当前筛选范围内的货柜、品牌和材质；"
        "可用页面顶部筛选器缩小范围。"
    )
    departments = raw_df.get(
        "department", pd.Series("", index=raw_df.index)
    ).fillna("").astype(str).str.strip()
    department_names = departments.drop_duplicates().tolist()
    for department in department_names:
        rows = raw_df[departments == department]
        if len(department_names) > 1:
            st.markdown(f"**{department or '未分类部门'}**")
        _render_container_summary_table(rows)


def _render_container_summary_table(raw_df):
    display_df = build_container_display(raw_df, include_cost=False)
    summary_df = build_container_inventory_summary(display_df)
    if summary_df.empty:
        return
    item_columns = [
        column for column in summary_df.columns
        if column not in {"材质", "颜色", "总件数"}
    ]
    st.dataframe(
        summary_df,
        hide_index=True,
        width="stretch",
        column_config={
            "总件数": st.column_config.NumberColumn("总件数", format="%d"),
            **{
                item: st.column_config.NumberColumn(
                    _item_label(item), format="%d"
                )
                for item in item_columns
            },
        },
    )


def render_container_detail(
    display_df, container_key, editable_cost=False
):
    detail_df = display_df[display_df["货柜记录ID"] == container_key].copy()
    if detail_df.empty:
        return
    container_no = detail_df["货柜号"].iloc[0] or detail_df["批次标识"].iloc[0]
    st.subheader(f"{container_no} 明细")
    total_quantity, total_cost = calculate_container_totals(detail_df)
    if total_cost is None:
        st.metric("总数量", f"{total_quantity:,} 件")
    else:
        quantity_col, cost_col = st.columns(2)
        quantity_col.metric("总数量", f"{total_quantity:,} 件")
        cost_col.metric("总成本", f"${total_cost:,.2f}")
    hidden = [
        "货柜记录ID", "批次标识", "发货日期", "运输天数", "预计到货日期",
        "实际到货日期", "实际到货时间（纽约）", "货柜号", "状态",
    ]
    detail_df = detail_df.drop(columns=hidden)
    item_columns = get_container_item_columns(display_df)
    front = ["部门", "品类", "品牌", "材质", "颜色", "备注"]
    cost = ["成本"] if "成本" in detail_df.columns else []
    if "型号" in detail_df.columns:
        detail_df = detail_df[[
            *front[:-1], *cost, "型号", "数量", "备注",
        ]]
    else:
        detail_df = detail_df[[*front, *cost, *item_columns, "总件数"]]
    config = {
        "备注": st.column_config.TextColumn("备注", width="large"),
        "型号": st.column_config.TextColumn("型号"),
        "数量": st.column_config.NumberColumn("数量", format="%d"),
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
            "成本", min_value=0.0, step=0.0001, format="%.4f",
            disabled=not editable_cost,
        )
    if editable_cost and "成本" in detail_df.columns:
        edited_detail_df = st.data_editor(
            detail_df,
            hide_index=True,
            width="stretch",
            column_config=config,
            disabled=[
                column for column in detail_df.columns
                if column != "成本"
            ],
            key=f"container_detail_cost_editor_{container_key}",
        )
    else:
        st.dataframe(
            detail_df, hide_index=True, width="stretch",
            column_config=config,
        )
        edited_detail_df = detail_df
    packaging_df = build_container_packaging_summary(display_df, container_key)
    render_packaging_check(packaging_df)
    return edited_detail_df


def calculate_container_totals(detail_df):
    if detail_df.empty:
        return 0, None
    quantities = pd.to_numeric(
        detail_df["总件数"], errors="coerce"
    ).fillna(0)
    total_quantity = int(quantities.sum())
    if "成本" not in detail_df.columns:
        return total_quantity, None
    unit_costs = pd.to_numeric(
        detail_df["成本"], errors="coerce"
    ).fillna(0)
    return total_quantity, float((quantities * unit_costs).sum())


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
