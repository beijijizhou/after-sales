import pandas as pd
import streamlit as st
from hashlib import sha1

from db.inventory.master_data import (
    load_master_data,
    load_sku_catalog,
    update_skus,
)
from ui.inventory.i18n import t
from ui.inventory.sku.create import render_create_skus
from ui.inventory.sku.master_forms import render_master_data_forms


def render_sku_management(
    supabase, selected_department, can_manage, sku_filters=None,
):
    try:
        departments, categories, brands = load_master_data(supabase)
    except Exception as error:
        st.error(f"{t('SKU 主数据加载失败')}：{error}")
        return
    active_departments = departments[
        departments.get("is_active", False) == True  # noqa: E712
    ]
    if active_departments.empty:
        st.info(t("请先建立库存部门"))
        render_master_data_forms(supabase, departments)
        return

    department_codes = active_departments["code"].tolist()
    department_code = (
        selected_department
        if selected_department in department_codes
        else department_codes[0]
    )
    department = active_departments[
        active_departments["code"] == department_code
    ].iloc[0].to_dict()
    st.caption(
        f"{t('SKU 所属部门')}：{department_code}"
    )

    if not can_manage:
        _render_catalog(supabase, department_code, sku_filters)
        return

    catalog_tab, create_tab, edit_tab, master_tab = st.tabs(
        [t("SKU 目录"), t("新增 SKU"), t("修改 SKU"), t("基础资料")]
    )
    with catalog_tab:
        _render_catalog(supabase, department_code, sku_filters)
    with create_tab:
        render_create_skus(
            supabase, department, categories, brands
        )
    with edit_tab:
        _render_editor(
            supabase, department, categories, brands, sku_filters
        )
    with master_tab:
        render_master_data_forms(supabase, departments)


def _render_catalog(supabase, department_code, sku_filters=None):
    catalog = load_sku_catalog(supabase, department_code)
    if catalog.empty:
        st.info(t("当前部门暂无 SKU"))
        return
    active_only = st.toggle(t("只看启用 SKU"), value=True)
    if active_only:
        catalog = catalog[catalog["is_active"] == True]  # noqa: E712
    catalog = catalog.assign(
        规格=catalog["model"].fillna(catalog["size"])
    )
    catalog = filter_sku_editor_source(catalog, sku_filters)
    display = _display_catalog(catalog)
    st.metric(t("SKU 数量"), len(display))
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        height=min(max((len(display) + 1) * 35 + 8, 220), 800),
    )


def _render_editor(
    supabase, department, categories, brands, sku_filters=None
):
    catalog = load_sku_catalog(supabase, department["code"])
    if catalog.empty:
        st.info(t("当前部门暂无可修改 SKU"))
        return
    department_categories = categories[
        categories["department_id"] == department["id"]
    ]
    category_names = department_categories["name"].tolist()
    active_brands = brands[
        brands.get("is_active", False) == True  # noqa: E712
    ]
    brand_names = ["", *active_brands.get("name", []).tolist()]
    source = catalog.assign(
        规格=catalog["model"].fillna(catalog["size"])
    )
    columns = [
        "id", "sku_code", "sku_name", "category", "brand",
        "material", "color", "规格", "unit", "quantity", "is_active",
    ]
    source = source[columns]
    filtered = filter_sku_editor_source(source, sku_filters)
    st.caption(f"已筛选 {len(filtered)} / {len(source)} 个 SKU")
    if filtered.empty:
        st.info("当前筛选条件下没有 SKU")
        return
    version = st.session_state.get("sku_master_editor_version", 0)
    signature = sha1(
        "|".join(filtered["id"].astype(str)).encode()
    ).hexdigest()[:10]
    edited = pd.DataFrame(st.data_editor(
        filtered,
        hide_index=True,
        width="stretch",
        disabled=["id", "sku_code", "sku_name", "quantity"],
        column_config={
            "id": None,
            "sku_code": st.column_config.TextColumn(t("SKU 编号")),
            "sku_name": st.column_config.TextColumn(
                t("SKU 名称")
            ),
            "category": st.column_config.SelectboxColumn(
                t("品类"), options=category_names, required=True
            ),
            "brand": st.column_config.SelectboxColumn(
                t("品牌"), options=brand_names
            ),
            "material": st.column_config.TextColumn(t("材质")),
            "color": st.column_config.TextColumn(t("颜色")),
            "规格": st.column_config.TextColumn(t("尺码 / 型号")),
            "unit": st.column_config.TextColumn(t("单位"), required=True),
            "quantity": st.column_config.NumberColumn(
                t("当前库存"), format="%d"
            ),
            "is_active": st.column_config.CheckboxColumn(t("启用")),
        },
        key=(
            f"sku_master_editor_{department['id']}_{version}_{signature}"
        ),
    ))
    st.caption(
        f"{t('SKU 修改历史说明')} SKU 名称会按品类、品牌、材质、颜色和规格自动生成。"
    )
    if not st.button(t("保存 SKU 修改"), width="stretch"):
        return
    try:
        complete_edited = source.set_index("id")
        complete_edited.update(edited.set_index("id"))
        complete_edited = complete_edited.reset_index()
        updated = update_skus(
            supabase, source, complete_edited,
            department_categories, brands,
        )
    except Exception as error:
        st.error(f"{t('SKU 修改失败')}：{error}")
        return
    if not updated:
        st.info(t("没有需要保存的修改"))
        return
    st.session_state["inventory_saved_message"] = (
        t("已更新 SKU").format(count=updated)
    )
    st.session_state["sku_master_editor_version"] = version + 1
    st.rerun()


def filter_sku_editor_source(source, selections=None):
    result = source.copy()
    selections = selections or {}
    show_phone_cases = selections.get("category") == "手机壳"
    if not show_phone_cases and "category" in result.columns:
        result = result[result["category"] != "手机壳"]
    for field, value in selections.items():
        if isinstance(value, (list, tuple, set)) and value:
            result = result[result[field].isin(value)]
        elif value and value != "全部":
            result = result[
                result[field].fillna("").astype(str).str.strip() == value
            ]
    return result.reset_index(drop=True)


def _display_catalog(catalog):
    result = catalog.assign(
        规格=catalog["model"].fillna(catalog["size"])
    ).rename(columns={
        "sku_code": t("SKU 编号"), "sku_name": t("SKU 名称"),
        "category": t("品类"), "brand": t("品牌"),
        "material": t("材质"), "color": t("颜色"),
        "规格": t("规格"), "unit": t("单位"),
        "quantity": t("当前库存"), "is_active": t("状态"),
    })
    result[t("状态")] = result[t("状态")].map({
        True: t("启用"), False: t("停用")
    })
    columns = [
        "SKU 编号", "SKU 名称", "品类", "品牌", "材质",
        "颜色", "规格", "单位", "当前库存", "状态",
    ]
    return result[[t(column) for column in columns]]
