from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from db.inventory import DEFAULT_DEPARTMENT, INVENTORY_CATEGORIES, SIZE_COLUMNS
from db.inventory.container import (
    CONTAINER_STATUSES,
    build_container_display,
    build_container_template,
    create_inventory_containers,
    load_inventory_containers,
    normalize_container_rows,
)
from utils.auth import has_permission


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_container_form(supabase):
    st.subheader("新增货柜安排")
    today = datetime.now(NY_TIMEZONE).date()
    form_version = st.session_state.get("container_form_version", 0)
    default_df = build_container_template(today + timedelta(days=10))

    edited_df = st.data_editor(
        default_df,
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        key=f"inventory_container_editor_{form_version}",
        column_config={
            "预计到货日期": st.column_config.DateColumn("预计到货日期", required=True),
            "货柜号": st.column_config.TextColumn("货柜号"),
            "部门": st.column_config.TextColumn("部门", required=True),
            "品类": st.column_config.SelectboxColumn("品类", options=["", *INVENTORY_CATEGORIES], required=False),
            "品牌": st.column_config.TextColumn("品牌"),
            "材质": st.column_config.TextColumn("材质", required=True),
            "颜色": st.column_config.TextColumn("颜色", required=True),
            **{size: st.column_config.NumberColumn(size, min_value=0, step=1) for size in SIZE_COLUMNS},
            "状态": st.column_config.SelectboxColumn("状态", options=CONTAINER_STATUSES, required=True),
            "备注": st.column_config.TextColumn("备注"),
        },
    )

    if st.button("保存货柜安排", use_container_width=True):
        try:
            cleaned_df = normalize_container_rows(edited_df)
            if cleaned_df.empty:
                st.warning("请先填写有效货柜安排")
                return
            create_inventory_containers(supabase, cleaned_df)
            st.session_state["container_form_version"] = form_version + 1
            st.success(f"已保存 {len(cleaned_df)} 条货柜安排")
            st.rerun()
        except Exception as e:
            st.error(f"保存失败：{e}")
            st.info("如果这是第一次使用货柜安排页，请先在 Supabase SQL Editor 运行 sql/inventory_containers.sql")


def render_container_table(supabase):
    st.subheader("货柜安排明细")
    today = datetime.now(NY_TIMEZONE).date()
    col1, col2 = st.columns(2)
    start_date = col1.date_input("开始日期", value=today - timedelta(days=7), key="container_start_date")
    end_date = col2.date_input("结束日期", value=today + timedelta(days=60), key="container_end_date")
    department = st.text_input("部门", value=DEFAULT_DEPARTMENT, key="container_department").strip()

    try:
        raw_df = load_inventory_containers(supabase, start_date, end_date, department=department)
    except Exception as e:
        st.error(f"货柜安排加载失败：{e}")
        st.info("如果这是第一次使用货柜安排页，请先在 Supabase SQL Editor 运行 sql/inventory_containers.sql")
        return

    display_df = build_container_display(raw_df, include_cost=has_permission("can_view_cost"))
    if display_df.empty:
        st.info("当前日期范围内暂无货柜安排")
        return

    total_quantity = int(display_df["总件数"].sum())
    pending_quantity = int(display_df[display_df["状态"] == "未到货"]["总件数"].sum())
    col1, col2, col3 = st.columns(3)
    col1.metric("总件数", total_quantity)
    col2.metric("未到货件数", pending_quantity)
    col3.metric("SKU 行数", len(display_df))

    column_config = {
        "预计到货日期": st.column_config.DateColumn("预计到货日期"),
        **{size: st.column_config.NumberColumn(size, format="%d") for size in SIZE_COLUMNS},
        "总件数": st.column_config.NumberColumn("总件数", format="%d"),
    }
    if "成本" in display_df.columns:
        column_config["成本"] = st.column_config.NumberColumn("成本", format="%.2f")

    st.dataframe(display_df, hide_index=True, use_container_width=True, column_config=column_config)


def render_inventory_container_page(supabase):
    st.title("货柜安排")
    if has_permission("can_edit_container"):
        render_container_form(supabase)
    else:
        st.info("当前账号只能查看货柜安排，不能新增或修改")
    render_container_table(supabase)
