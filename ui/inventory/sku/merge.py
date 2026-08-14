"""Auditable SKU group merge workflow."""

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from db.inventory.master_data import (
    build_sku_group_merge_preview,
    build_sku_merge_groups,
    compatible_merge_targets,
    group_key,
    group_label,
    load_sku_merge_rules,
    merge_sku_groups,
)
from ui.table_layout import fit_table_height
from utils.auth import get_current_operator_name


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_sku_merge(supabase, department, catalog):
    st.subheader("SKU 并入")
    st.caption(
        "把一个品牌的同品类、材质、颜色和全部尺码并入目标品牌。"
        "当前库存、仓库分布和成本批次会转移，来源 SKU 归零并停用；"
        "历史流水保留原身份，后续同来源入库自动转入目标 SKU。"
    )
    if not _render_current_rules(supabase, department):
        return
    groups = build_sku_merge_groups(catalog)
    if groups.empty:
        st.info("当前部门没有可并入的 SKU")
        return
    options = {group_key(row): group_label(group_key(row)) for row in groups.to_dict("records")}
    source_key = st.selectbox(
        "来源 SKU 组", list(options), format_func=options.get,
        key=f"sku_merge_source_{department}",
    )
    available_brands = sorted({
        str(value or "").strip()
        for value in catalog.get("brand", [])
        if str(value or "").strip()
    })
    target_keys = compatible_merge_targets(
        groups, source_key, available_brands=available_brands
    )
    if not target_keys:
        st.info("当前来源没有同品类、材质和颜色的其他目标品牌 SKU。")
        return
    target_key = st.selectbox(
        "目标 SKU 组", target_keys, format_func=group_label,
        key=f"sku_merge_target_{department}",
    )
    preview = build_sku_group_merge_preview(catalog, source_key, target_key)
    if preview.empty:
        st.info("来源与目标都没有库存，不需要并入。")
        return
    st.markdown("#### 并入前后核对")
    st.dataframe(
        preview, hide_index=True, width="stretch",
        height=fit_table_height(preview),
    )
    total = int(preview["来源当前库存"].sum())
    st.warning(
        f"确认后将把 {source_key[1]} 的 {total:,} 件当前库存并入 "
        f"{target_key[1]}，来源 SKU 将归零并停用。"
    )
    confirmed = st.checkbox(
        "我已核对来源、目标和各尺码数量",
        key=f"sku_merge_confirm_{department}",
    )
    if not st.button(
        "确认并入", type="primary", width="stretch", disabled=not confirmed,
        key=f"sku_merge_submit_{department}",
    ):
        return
    try:
        result = merge_sku_groups(
            supabase, department, source_key, target_key,
            datetime.now(NY_TIMEZONE).date(), get_current_operator_name(),
        )
    except Exception as error:
        st.error(f"SKU 并入失败：{error}")
        return
    moved_quantity = (
        int(result.get("moved_quantity") or total)
        if isinstance(result, dict) else total
    )
    st.session_state["inventory_saved_message"] = (
        f"SKU 并入完成：{source_key[1]} → {target_key[1]}，"
        f"转移 {moved_quantity:,} 件"
    )
    st.rerun()


def _render_current_rules(supabase, department):
    st.markdown("#### 当前并入情况")
    try:
        rules = load_sku_merge_rules(supabase, department)
    except Exception as error:
        st.warning(
            "SKU 并入功能尚未安装，请先执行 "
            "sql/inventory/operations/sku_merge_rules.sql。"
        )
        st.caption(str(error))
        return False
    if rules.empty:
        st.info("当前没有 SKU 并入规则")
        return True
    display = rules.rename(columns={
        "category": "品类", "source_brand": "来源品牌",
        "target_brand": "目标品牌", "material": "材质", "color": "颜色",
        "status": "状态", "created_by": "操作人", "created_at": "设置时间",
    })
    display["状态"] = display["状态"].map({"active": "生效中", "inactive": "已停用"}).fillna(display["状态"])
    st.dataframe(
        display[["状态", "品类", "材质", "颜色", "来源品牌", "目标品牌", "操作人", "设置时间"]],
        hide_index=True, width="stretch", height=fit_table_height(display),
    )
    return True
