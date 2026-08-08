import pandas as pd
import streamlit as st
from hashlib import sha1

from db.inventory import SIZE_COLUMNS
from db.inventory.master_data import (
    build_sku_merge_preview,
    load_master_data,
    load_materials,
    load_sku_catalog,
    update_skus,
)
from ui.inventory.i18n import t
from ui.inventory.sku.create import render_create_skus
from ui.inventory.sku.master_forms import render_master_data_forms
from utils.auth import get_current_operator_name


def render_sku_management(
    supabase, selected_department, can_manage, sku_filters=None,
    selected_category="",
):
    try:
        departments, categories, brands = load_master_data(supabase)
        materials = load_materials(supabase)
    except Exception as error:
        st.error(f"{t('SKU 主数据加载失败')}：{error}")
        return
    active_departments = departments[
        departments.get("is_active", False) == True  # noqa: E712
    ]
    if active_departments.empty:
        st.info(t("请先建立库存部门"))
        render_master_data_forms(supabase, departments, categories)
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
        [t("SKU 目录"), t("新增 SKU"), t("修改 SKU"), t("新增 SKU 选项")]
    )
    with catalog_tab:
        _render_catalog(supabase, department_code, sku_filters)
    with create_tab:
        render_create_skus(
            supabase, department, categories, brands, materials,
            selected_category=selected_category,
        )
    with edit_tab:
        _render_editor(
            supabase, department, categories, brands, materials, sku_filters
        )
    with master_tab:
        render_master_data_forms(supabase, departments, categories)


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
    supabase, department, categories, brands, materials, sku_filters=None
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
    active_materials = materials[
        materials.get("is_active", False) == True  # noqa: E712
    ]
    source = catalog.assign(
        规格=catalog["model"].fillna(catalog["size"])
    )
    columns = [
        "id", "sku_code", "sku_name", "category", "brand",
        "material", "color", "规格", "unit", "quantity", "is_active",
    ]
    source = source[columns]
    material_names = sorted({
        *active_materials.get("name", []).tolist(),
        *source.get("material", []).dropna().tolist(),
    })
    filtered = filter_sku_editor_source(source, sku_filters)
    st.caption(f"已筛选 {len(filtered)} / {len(source)} 个 SKU")
    if filtered.empty:
        st.info("当前筛选条件下没有 SKU")
        return
    version = st.session_state.get("sku_master_editor_version", 0)
    signature = sha1(
        "|".join(filtered["id"].astype(str)).encode()
    ).hexdigest()[:10]
    wide_mode = uses_standard_sku_sizes(filtered)
    editor_source = (
        build_sku_editor_wide_source(filtered) if wide_mode else filtered
    )
    disabled_columns = (
        ["_group_key", *[size for size in SIZE_COLUMNS if size in editor_source]]
        if wide_mode else ["id", "sku_code", "sku_name", "quantity"]
    )
    edited = pd.DataFrame(st.data_editor(
        editor_source,
        hide_index=True,
        width="stretch",
        disabled=disabled_columns,
        column_config={
            "id": None,
            "_group_key": None,
            "sku_code": None,
            "sku_name": None,
            "category": st.column_config.SelectboxColumn(
                t("品类"), options=category_names, required=True
            ),
            "brand": st.column_config.SelectboxColumn(
                t("品牌"), options=brand_names
            ),
            "material": st.column_config.SelectboxColumn(
                t("材质"), options=["", *material_names]
            ),
            "color": st.column_config.TextColumn(t("颜色")),
            "规格": st.column_config.TextColumn(t("尺码 / 型号")),
            "unit": st.column_config.TextColumn(t("单位"), required=True),
            "quantity": st.column_config.NumberColumn(
                t("当前库存"), format="%d"
            ),
            **{
                size: st.column_config.NumberColumn(
                    size, format="%d", help=t("当前库存")
                )
                for size in SIZE_COLUMNS if size in editor_source.columns
            },
            "is_active": st.column_config.CheckboxColumn(t("启用")),
        },
        key=(
            f"sku_master_editor_{department['id']}_{version}_{signature}"
        ),
    ))
    st.caption("修改会应用到当前行包含的全部尺码。")
    edited_rows = (
        expand_sku_editor_wide_rows(filtered, edited)
        if wide_mode else edited
    )
    complete_edited = source.set_index("id")
    complete_edited.update(edited_rows.set_index("id"))
    complete_edited = complete_edited.reset_index()
    merge_preview = build_sku_merge_preview(source, complete_edited)
    if merge_preview:
        merged_skus = sum(item["overlap_count"] for item in merge_preview)
        moved_quantity = sum(item["quantity"] for item in merge_preview)
        routes = "；".join(
            f"{item['old_brand']} → {item['new_brand']}"
            for item in merge_preview
        )
        st.warning(
            f"发现重复 SKU：{routes}。保存后会合并 {merged_skus} 个相同尺码，"
            f"涉及当前库存 {moved_quantity:,} 件，并同步货柜、流水和历史记录。"
        )
    if not st.button(t("保存 SKU 修改"), width="stretch"):
        return
    try:
        updated = update_skus(
            supabase, source, complete_edited,
            department_categories, brands, materials,
            department_code=department["code"],
            changed_by=get_current_operator_name(),
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


def uses_standard_sku_sizes(source):
    specifications = {
        str(value).strip() for value in pd.DataFrame(source).get("规格", [])
        if not pd.isna(value) and str(value).strip()
    }
    return bool(specifications) and specifications.issubset(set(SIZE_COLUMNS))


def build_sku_editor_wide_source(source):
    dimensions = [
        "category", "brand", "material", "color", "unit", "is_active",
    ]
    prepared = pd.DataFrame(source).copy()
    prepared[[*dimensions[:-1]]] = prepared[[*dimensions[:-1]]].fillna("")
    prepared["is_active"] = prepared["is_active"].fillna(True).astype(bool)
    available_sizes = [
        size for size in SIZE_COLUMNS
        if size in set(prepared["规格"].dropna().astype(str))
    ]
    rows = []
    for keys, group in prepared.groupby(dimensions, dropna=False, sort=False):
        row = dict(zip(dimensions, keys))
        row["_group_key"] = _sku_editor_group_key(group)
        quantities = group.groupby("规格")["quantity"].sum().to_dict()
        row.update({size: quantities.get(size, pd.NA) for size in available_sizes})
        rows.append(row)
    return pd.DataFrame(
        rows, columns=["_group_key", *dimensions, *available_sizes]
    )


def expand_sku_editor_wide_rows(source, edited):
    dimensions = [
        "category", "brand", "material", "color", "unit", "is_active",
    ]
    prepared = pd.DataFrame(source).copy()
    prepared[[*dimensions[:-1]]] = prepared[[*dimensions[:-1]]].fillna("")
    prepared["is_active"] = prepared["is_active"].fillna(True).astype(bool)
    group_keys = {}
    for _, group in prepared.groupby(dimensions, dropna=False, sort=False):
        key = _sku_editor_group_key(group)
        group_keys.update({item_id: key for item_id in group["id"]})
    prepared["_group_key"] = prepared["id"].map(group_keys)
    changes = pd.DataFrame(edited)[["_group_key", *dimensions]]
    result = prepared.drop(columns=dimensions).merge(
        changes, on="_group_key", how="left", validate="many_to_one"
    )
    return result.drop(columns="_group_key")


def _sku_editor_group_key(group):
    identifiers = sorted(str(value) for value in group["id"])
    return sha1("|".join(identifiers).encode()).hexdigest()[:12]


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
    source = catalog.assign(
        规格=catalog["model"].fillna(catalog["size"])
    )
    specifications = set(source["规格"].dropna().astype(str))
    if specifications and specifications.issubset(set(SIZE_COLUMNS)):
        index = [
            "category", "brand", "material", "color", "unit", "is_active",
        ]
        source[index] = source[index].fillna("")
        result = (
            source.groupby([*index, "规格"], dropna=False, sort=False)["quantity"]
            .sum()
            .unstack(fill_value=0)
            .reset_index()
        )
        for size in SIZE_COLUMNS:
            if size not in result.columns:
                result[size] = 0
        result = result.rename(columns={
            "category": t("品类"), "brand": t("品牌"),
            "material": t("材质"), "color": t("颜色"),
            "unit": t("单位"), "is_active": t("状态"),
        })
        result[t("状态")] = result[t("状态")].map({
            True: t("启用"), False: t("停用")
        })
        dimensions = ["品类", "品牌", "材质", "颜色", "单位", "状态"]
        return result[[t(column) for column in dimensions] + SIZE_COLUMNS]

    result = source.rename(columns={
        "category": t("品类"), "brand": t("品牌"),
        "material": t("材质"), "color": t("颜色"),
        "规格": t("规格"), "unit": t("单位"),
        "quantity": t("当前库存"), "is_active": t("状态"),
    })
    result[t("状态")] = result[t("状态")].map({
        True: t("启用"), False: t("停用")
    })
    columns = [
        "品类", "品牌", "材质", "颜色", "规格", "单位", "当前库存", "状态",
    ]
    return result[[t(column) for column in columns]]
