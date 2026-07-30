import pandas as pd
import streamlit as st

from db.inventory.master_data import (
    initialize_sku_inventory,
    load_uninitialized_skus,
)
from ui.inventory.i18n import t
from utils.auth import get_current_operator_name


def render_inventory_initialization(
    supabase, department, category, can_edit
):
    try:
        pending = load_uninitialized_skus(
            supabase, department, category
        )
    except Exception as error:
        st.error(f"{t('待初始化库存加载失败')}：{error}")
        return

    if pending.empty:
        st.success(t("当前范围没有待初始化的 SKU"))
        return

    st.warning(
        t("还有 {count} 个 SKU 尚未录入初始库存").format(
            count=len(pending)
        )
    )
    st.caption(t("这里只显示库存为零且从未有过入库记录的 SKU"))
    source = _build_editor_source(pending)
    version = st.session_state.get(
        "inventory_initialization_version", 0
    )
    edited = pd.DataFrame(st.data_editor(
        source,
        hide_index=True,
        width="stretch",
        disabled=[
            "sku_code", "sku_name", "category", "brand",
            "material", "color", "size", "unit",
        ],
        column_config={
            "sku_code": st.column_config.TextColumn(t("SKU 编号")),
            "sku_name": st.column_config.TextColumn(t("SKU 名称")),
            "category": st.column_config.TextColumn(t("品类")),
            "brand": st.column_config.TextColumn(t("品牌")),
            "material": st.column_config.TextColumn(t("材质")),
            "color": st.column_config.TextColumn(t("颜色")),
            "size": st.column_config.TextColumn(t("尺码 / 型号")),
            "unit": st.column_config.TextColumn(t("单位")),
            "初始库存": st.column_config.NumberColumn(
                t("初始库存"), min_value=0, step=1, format="%d"
            ),
        },
        key=f"inventory_initialization_{department}_{category}_{version}",
    ))
    if not can_edit:
        st.info(t("当前账号只能查看待初始化清单"))
        return
    selected = edited[
        pd.to_numeric(
            edited["初始库存"], errors="coerce"
        ).fillna(0) > 0
    ]
    st.metric(t("本次录入 SKU"), len(selected))
    if not st.button(t("保存初始库存"), width="stretch"):
        return
    if selected.empty:
        st.warning(t("请先填写至少一个初始库存数量"))
        return
    try:
        saved = initialize_sku_inventory(
            supabase,
            department,
            selected,
            get_current_operator_name(),
        )
    except Exception as error:
        st.error(f"{t('初始库存保存失败')}：{error}")
        return
    st.session_state["inventory_saved_message"] = (
        t("已完成 {count} 个 SKU 的库存初始化").format(count=saved)
    )
    st.session_state["inventory_initialization_version"] = version + 1
    st.rerun()


def _build_editor_source(pending):
    source = pending.copy()
    source["size"] = source["model"].fillna(source["size"])
    source["初始库存"] = 0
    columns = [
        "sku_code", "sku_name", "category", "brand", "material",
        "color", "size", "unit", "初始库存",
    ]
    return source[columns].sort_values(
        ["category", "material", "color", "size"],
        kind="stable",
    ).reset_index(drop=True)
