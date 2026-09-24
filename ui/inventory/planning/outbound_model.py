"""Shared manual-outbound consumption-model view for every inventory category."""

import pandas as pd
import streamlit as st

from db.inventory.planning.outbound_consumption import load_outbound_consumption
from ui.inventory.i18n import t
from ui.inventory.planning.comparison import render_model_detail
from ui.planning import render_consumption_window_input
from ui.table_layout import fit_table_height


APPAREL_CATEGORIES = {"黑白短袖", "彩色短袖", "卫衣"}


def render_outbound_consumption_model(
    supabase, department, category, current_date, visible_sizes=None,
    *, brands=None, materials=None, colors=None, sizes=None,
):
    window_days = render_consumption_window_input(
        st, key=f"inventory_consumption_lookback_{department}_{category}",
    )
    if not category:
        st.info("请先选择一个品类，再查看该品类的出库消耗模型。")
        return
    try:
        result = load_outbound_consumption(
            supabase, department, category, current_date,
            window_days=window_days, brands=brands, materials=materials,
            colors=colors, sizes=sizes,
        )
        model = result.model
        if visible_sizes and not model.empty:
            model = model[model["尺码"].isin(visible_sizes)]
    except Exception as error:
        st.error(f"{t('消耗模型加载失败')}：{error}")
        return

    st.subheader(f"{category}仓库消耗模型")
    st.caption(
        f"以最近 {window_days} 天仓库人工登记的实际出库为唯一正式口径；"
        "平台生产数据只在系统数据参考与生产数据页面独立核对。"
    )
    if model.empty:
        st.info(f"最近 {window_days} 天暂无仓库人工出库记录")
        return

    total = pd.to_numeric(model["每日消耗"], errors="coerce").fillna(0).sum()
    metrics = st.columns(3)
    metrics[0].metric("仓库模型日耗", f"{total:,.1f} 件")
    metrics[1].metric("人工登记天数", f"{result.recorded_days} 天")
    metrics[2].metric("统计窗口", f"{window_days} 天")
    material_scope = sorted({
        str(value).strip() for value in (materials or []) if str(value).strip()
    })
    st.caption(
        "当前模型严格沿用页面顶部层级筛选；材质范围："
        f"{'、'.join(material_scope) or '全部当前材质'}。"
    )
    st.caption(
        "没有登记的日期不会被当作零；从某 SKU 首次出库起，"
        "按该品类已登记的出库日计算，一次出库也能形成初始模型。"
    )
    if category in APPAREL_CATEGORIES:
        display = model.groupby(
            ["颜色", "尺码"], as_index=False
        )["每日消耗"].sum().rename(columns={"每日消耗": "仓库出库日均"})
        render_model_detail(display, "仓库出库日均", "仓库出库模型")
        return
    _render_hierarchy_model(model)


def _render_hierarchy_model(model):
    dimensions = [
        column for column in ["品牌", "材质", "颜色", "尺码"]
        if model[column].astype(str).str.strip().ne("").any()
    ]
    columns = [*dimensions, "每日消耗", "有效数据天数", "窗口总消耗"]
    st.dataframe(
        model[columns], hide_index=True, width="stretch",
        height=fit_table_height(model),
    )
