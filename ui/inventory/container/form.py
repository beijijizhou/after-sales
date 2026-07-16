from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from db.inventory import SIZE_COLUMNS
from db.inventory.container.repository import create_inventory_containers
from db.inventory.container.packaging import build_container_packaging_preview
from db.inventory.container.tables import (
    CONTAINER_STATUSES,
    build_container_schedule_preview,
    build_container_template,
    normalize_container_rows,
)
from utils.auth import get_current_operator_name, has_permission
from ui.inventory.container.tables import render_packaging_check


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_container_form(supabase, department=None, category=None):
    st.subheader("新增货柜安排")
    today = datetime.now(NY_TIMEZONE).date()
    form_version = st.session_state.get("container_form_version", 0)
    default_df = build_container_template(today)
    if department:
        default_df["部门"] = department
    if category:
        default_df["品类"] = category
    can_view_cost = has_permission("can_view_cost")
    if not can_view_cost:
        default_df = default_df.drop(columns=["成本"])

    edited_df = st.data_editor(
        default_df,
        hide_index=True,
        num_rows="dynamic",
        width="stretch",
        key=(
            f"inventory_container_editor_{form_version}_"
            f"{department or 'all'}_{category or 'all'}"
        ),
        column_config={
            "发货日期": st.column_config.DateColumn("发货日期", required=True),
            "预计运输天数": st.column_config.NumberColumn(
                "预计运输天数", min_value=1, step=1, required=True
            ),
            "货柜号": st.column_config.TextColumn("货柜号"),
            "部门": st.column_config.TextColumn("部门", required=True),
            "品类": st.column_config.TextColumn("品类（可选）"),
            "品牌": st.column_config.TextColumn("品牌"),
            "材质": st.column_config.TextColumn("材质", required=True),
            "颜色": st.column_config.TextColumn("颜色", required=True),
            **({
                "成本": st.column_config.NumberColumn(
                    "成本", min_value=0.0, format="%.2f"
                )
            } if can_view_cost else {}),
            **{
                size: st.column_config.NumberColumn(size, min_value=0, step=1)
                for size in SIZE_COLUMNS
            },
            "状态": st.column_config.SelectboxColumn(
                "状态", options=CONTAINER_STATUSES, required=True
            ),
            "备注": st.column_config.TextColumn("备注"),
        },
    )
    schedule_df = build_container_schedule_preview(edited_df)
    if not schedule_df.empty:
        st.caption("预计到货日期由发货日期加预计运输天数自动计算")
        st.dataframe(
            schedule_df,
            hide_index=True,
            width="stretch",
            column_config={
                "发货日期": st.column_config.DateColumn("发货日期"),
                "预计运输天数": st.column_config.NumberColumn(
                    "预计运输天数", format="%d 天"
                ),
                "预计到货日期": st.column_config.DateColumn("预计到货日期"),
            },
        )

    packaging_df = build_container_packaging_preview(edited_df)
    if not packaging_df.empty:
        st.caption("以下箱数/包装信息仅供仓库点数核对；系统仍按件数保存和计算。")
        render_packaging_check(packaging_df, title="保存前包装核对")

    if not st.button("保存货柜安排", width="stretch"):
        return
    try:
        cleaned_df = normalize_container_rows(edited_df)
        if cleaned_df.empty:
            st.warning("请先填写有效货柜安排")
            return
        create_inventory_containers(
            supabase, edited_df, operated_by=get_current_operator_name()
        )
        st.session_state["container_form_version"] = form_version + 1
        st.success(f"已保存 {len(cleaned_df)} 条货柜安排")
        st.rerun()
    except Exception as error:
        st.error(f"保存失败：{error}")
        st.info("请先在 Supabase SQL Editor 运行 sql/inventory_container_history.sql")
