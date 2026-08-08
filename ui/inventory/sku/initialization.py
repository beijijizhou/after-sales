from hashlib import sha1

import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS
from db.inventory.master_data import (
    initialize_sku_inventory,
    load_uninitialized_skus,
)
from ui.inventory.i18n import t
from ui.inventory.shared import filter_inventory_rows
from utils.auth import get_current_operator_name
from utils.sku_sorting import sort_sku_rows


def render_inventory_initialization(
    supabase, department, category, can_edit,
    brands=None, materials=None, colors=None, sizes=None,
):
    try:
        pending = load_uninitialized_skus(
            supabase, department, category
        )
    except Exception as error:
        st.error(f"{t('待初始化库存加载失败')}：{error}")
        return
    pending = filter_inventory_rows(
        pending, category, brands, materials, colors, sizes
    )

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
    wide_mode = uses_standard_size_columns(source)
    editor_source = (
        build_initialization_wide_source(source) if wide_mode
        else source.drop(columns=["sku_code", "sku_name"])
    )
    version = st.session_state.get(
        "inventory_initialization_version", 0
    )
    signature = build_initialization_signature(source)
    edited = pd.DataFrame(st.data_editor(
        editor_source,
        hide_index=True,
        width="stretch",
        disabled=[
            column for column in editor_source.columns
            if column not in ([*SIZE_COLUMNS] if wide_mode else ["初始库存"])
        ],
        column_config={
            "category": st.column_config.TextColumn(t("品类")),
            "brand": st.column_config.TextColumn(t("品牌")),
            "material": st.column_config.TextColumn(t("材质")),
            "color": st.column_config.TextColumn(t("颜色")),
            "size": st.column_config.TextColumn(t("尺码 / 型号")),
            "unit": st.column_config.TextColumn(t("单位")),
            "初始库存": st.column_config.NumberColumn(
                t("初始库存"), min_value=0, step=1, format="%d"
            ),
            **{
                size: st.column_config.NumberColumn(
                    size, min_value=0, step=1, format="%d"
                )
                for size in SIZE_COLUMNS if size in editor_source.columns
            },
        },
        key=(
            f"inventory_initialization_{department}_{category}_"
            f"{version}_{signature}"
        ),
    ))
    if not can_edit:
        st.info(t("当前账号只能查看待初始化清单"))
        return
    selected = (
        expand_initialization_wide_rows(edited, source) if wide_mode else edited
    )
    selected = selected[
        pd.to_numeric(
            selected["初始库存"], errors="coerce"
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
    return sort_sku_rows(
        source[columns],
        material="material",
        color="color",
        size="size",
        leading=["category"],
    )


def build_initialization_signature(source):
    values = [
        "" if pd.isna(value) else str(value)
        for value in pd.DataFrame(source).get("sku_code", [])
    ]
    return sha1("|".join(values).encode("utf-8")).hexdigest()[:10]


def uses_standard_size_columns(source):
    specifications = {
        str(value).strip() for value in pd.DataFrame(source).get("size", [])
        if not pd.isna(value) and str(value).strip()
    }
    return bool(specifications) and specifications.issubset(set(SIZE_COLUMNS))


def build_initialization_wide_source(source):
    dimensions = ["category", "brand", "material", "color", "unit"]
    available_sizes = [
        size for size in SIZE_COLUMNS
        if size in set(source["size"].dropna().astype(str))
    ]
    rows = []
    for keys, group in source.groupby(dimensions, dropna=False, sort=False):
        row = dict(zip(dimensions, keys if isinstance(keys, tuple) else [keys]))
        pending_sizes = set(group["size"].dropna().astype(str))
        row.update({
            size: 0 if size in pending_sizes else pd.NA
            for size in available_sizes
        })
        rows.append(row)
    return pd.DataFrame(rows, columns=[*dimensions, *available_sizes])


def expand_initialization_wide_rows(wide, allowed_source=None):
    dimensions = ["category", "brand", "material", "color", "unit"]
    size_columns = [size for size in SIZE_COLUMNS if size in wide.columns]
    result = wide.melt(
        id_vars=dimensions,
        value_vars=size_columns,
        var_name="size",
        value_name="初始库存",
    )
    if allowed_source is not None:
        allowed = pd.DataFrame(allowed_source)[[*dimensions, "size"]].drop_duplicates()
        result = result.merge(allowed, on=[*dimensions, "size"], how="inner")
    return result
