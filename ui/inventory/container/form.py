from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS
from db.inventory.container.repository import create_inventory_containers
from db.inventory.container.packaging import build_container_packaging_preview
from db.inventory.master_data.repository import load_sku_catalog
from db.inventory.container.tables import (
    CONTAINER_STATUSES,
    DEFAULT_TRANSIT_DAYS,
    build_container_schedule_preview,
    normalize_container_rows,
)
from utils.auth import get_current_operator_name, has_permission
from ui.inventory.container.tables import render_packaging_check
from ui.inventory.shared.linked_sku_table import linked_sku_options
from ui.table_layout import fit_table_height
from ui.inventory.container.form_models import (
    add_container_identity,
    build_container_form_rows,
    build_item_column_config as _build_item_column_config,
    container_identity_columns as _container_identity_columns,
    edited_total as _edited_total,
    empty_container_items as _empty_container_items,
    keep_container_items,
)


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_container_form(supabase, department=None, category=None):
    st.subheader("新增货柜安排")
    if not department:
        st.info("请先在页面顶部选择具体部门，再新增货柜安排")
        return
    today = datetime.now(NY_TIMEZONE).date()
    form_version = st.session_state.get("container_form_version", 0)
    can_view_cost = has_permission("can_view_cost")
    try:
        sku_catalog = load_sku_catalog(
            supabase, department, active_only=True
        )
    except Exception:
        st.error("SKU 资料加载失败，暂时无法新增货柜安排。")
        return
    if sku_catalog.empty:
        st.warning("当前部门没有可用 SKU，请先在 SKU 管理中新增。")
        return

    st.markdown("#### 货柜基本信息")
    first, second, third = st.columns([1, 1, 1.4])
    shipped_date = first.date_input(
        "发货日期", value=today,
        key=f"container_shipped_date_{form_version}",
    )
    transit_days = second.number_input(
        "预计运输天数", min_value=1, step=1, value=DEFAULT_TRANSIT_DAYS,
        key=f"container_transit_days_{form_version}",
    )
    container_no = third.text_input(
        "货柜号（可稍后补充）",
        key=f"container_no_{form_version}",
    )
    status_col, note_col = st.columns([1, 3])
    status = status_col.selectbox(
        "状态", CONTAINER_STATUSES,
        key=f"container_status_{form_version}",
    )
    container_note = note_col.text_input(
        "整柜备注（可选）", key=f"container_note_{form_version}",
    )

    items_key = (
        f"container_linked_items_{form_version}_"
        f"{department}_{category or 'all'}"
    )
    if items_key not in st.session_state:
        st.session_state[items_key] = _empty_container_items(department)
    st.markdown("#### 添加 SKU 明细")
    st.caption("按品类 → 材质 → 品牌 → 颜色联动选择；下游选项只显示有效 SKU 组合。")
    selected_identity = _render_container_sku_selector(
        sku_catalog, department, category, form_version
    )
    if st.button(
        "加入货柜明细",
        key=f"container_add_linked_sku_{form_version}",
        width="stretch",
    ):
        current_items = pd.DataFrame(st.session_state[items_key]).copy()
        updated, added = add_container_identity(
            current_items, selected_identity, department
        )
        st.session_state[items_key] = updated
        if added:
            st.rerun()
        else:
            st.warning("该 SKU 已在明细表中；请直接填写数量。")

    st.markdown("#### 货柜 SKU 表格")
    items = pd.DataFrame(st.session_state[items_key]).copy()
    if items.empty:
        st.info("请先通过上方联动选择器加入 SKU。")
        return
    edited_items = st.data_editor(
        items,
        hide_index=True,
        num_rows="fixed",
        width="stretch",
        key=f"inventory_container_editor_{form_version}_{department}_{category or 'all'}",
        column_config=_build_item_column_config(department, can_view_cost),
        disabled=_container_identity_columns(department),
        height=fit_table_height(items),
    )
    edited_items = keep_container_items(edited_items)
    st.session_state[items_key] = edited_items.reset_index(drop=True)
    edited_df = build_container_form_rows(
        edited_items,
        shipped_date=shipped_date,
        transit_days=transit_days,
        container_no=container_no,
        department=department,
        status=status,
        container_note=container_note,
    )
    schedule_df = build_container_schedule_preview(edited_df)
    if not schedule_df.empty:
        st.caption("预计到货日期由发货日期加预计运输天数自动计算")
        st.dataframe(
            schedule_df,
            hide_index=True,
            width="stretch",
            height=fit_table_height(schedule_df),
            column_config={
                "发货日期": st.column_config.DateColumn("发货日期"),
                "预计运输天数": st.column_config.NumberColumn(
                    "预计运输天数", format="%d 天"
                ),
                "预计到货日期": st.column_config.DateColumn("预计到货日期"),
            },
        )

    if department == "DTF":
        packaging_df = build_container_packaging_preview(edited_df)
        if not packaging_df.empty:
            st.caption("以下箱数/包装信息仅供仓库点数核对；系统仍按件数保存和计算。")
            render_packaging_check(packaging_df, title="保存前包装核对")

    st.metric("当前编辑总件数", f"{_edited_total(edited_df):,}")
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
        st.info("请先在 Supabase SQL Editor 运行 sql/inventory/containers/inventory_container_history.sql")


def _render_container_sku_selector(catalog, department, fixed_category, version):
    categories = sorted({
        str(value).strip() for value in catalog["category"].dropna()
        if str(value).strip()
    })
    category = fixed_category or _select_linked_value(
        "品类", categories, f"container_item_category_{version}"
    )
    scoped = catalog[catalog["category"] == category] if category else catalog
    columns = st.columns(4 if department != "DTF" else 3)
    all_options = linked_sku_options(scoped)
    material = _select_linked_value(
        "材质", all_options["materials"],
        f"container_item_material_{version}", columns[0],
    )
    material_options = linked_sku_options(scoped, material)
    brand = _select_linked_value(
        "品牌", material_options["brands"],
        f"container_item_brand_{version}", columns[1], allow_blank=True,
    )
    brand_options = linked_sku_options(scoped, material, brand or None)
    color = _select_linked_value(
        "颜色", brand_options["colors"],
        f"container_item_color_{version}", columns[2], allow_blank=True,
    )
    model = ""
    if department != "DTF":
        model_options = linked_sku_options(
            scoped, material, brand or None, color or None
        )["sizes"]
        model = _select_linked_value(
            "型号", model_options, f"container_item_model_{version}",
            columns[3],
        )
    return {
        "品类": category, "品牌": brand, "材质": material,
        "颜色": color, "型号": model,
    }


def _select_linked_value(
    label, options, key, container=None, allow_blank=False,
):
    target = container if container is not None else st
    choices = list(options)
    if allow_blank and not choices:
        choices = [""]
    if not choices:
        target.text_input(label, value="", disabled=True, key=f"{key}_empty")
        return ""
    if st.session_state.get(key) not in choices:
        st.session_state[key] = choices[0]
    return target.selectbox(label, choices, key=key)
