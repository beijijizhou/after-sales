import streamlit as st

from db.inventory.container.tables import (
    build_container_display,
    get_container_item_columns,
)
from ui.inventory.container.detail_tables import (
    calculate_container_totals,
    render_container_detail,
    render_packaging_check,
)
from ui.inventory.container.summary_tables import (
    render_container_inventory_summary,
    render_filtered_container_summary,
)
from ui.table_layout import fit_table_height


def render_container_records(
    raw_df, include_cost=False, group_by_department=None,
):
    if raw_df.empty:
        return
    departments = (
        raw_df["department"].fillna("").astype(str).str.strip()
        if "department" in raw_df.columns
        else None
    )
    should_group = (
        departments is not None and departments.nunique() > 1
        if group_by_department is None
        else bool(group_by_department and departments is not None)
    )
    if not should_group:
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
        "批次标识": st.column_config.TextColumn("货柜备注", width="medium"),
        "货柜号": st.column_config.TextColumn("实体货柜号", width="medium"),
        "发货日期": st.column_config.DateColumn("发货日期"),
        "运输天数": st.column_config.NumberColumn("运输天数", format="%d 天"),
        "预计到货日期": st.column_config.DateColumn("预计到货日期"),
        "实际到货日期": st.column_config.DateColumn("实际到货日期"),
        "实际到货时间（纽约）": st.column_config.TextColumn(
            "实际到货时间（纽约）"
        ),
        "确认到柜时间（纽约）": st.column_config.TextColumn(
            "确认到柜时间（纽约）"
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
        height=fit_table_height(table_df),
    )


def _item_label(value):
    return "yuan" if str(value).upper() == "YUAN" else value
