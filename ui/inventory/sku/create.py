import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS
from db.inventory.master_data import create_skus
from ui.inventory.i18n import t
from utils.auth import get_current_operator_name


def render_create_skus(
    supabase, department, categories, brands, materials,
    selected_category="",
):
    st.subheader(t("新增 SKU"))
    department_categories = categories[
        (categories["department_id"] == department["id"])
        & (categories["is_active"] == True)  # noqa: E712
    ]
    if department_categories.empty:
        st.info(t("当前部门还没有品类，请先在“新增 SKU 选项”中新增品类。"))
        return

    category_names = department_categories["name"].tolist()
    category_key = f"create_sku_category_{department['id']}"
    if selected_category in category_names:
        st.session_state[category_key] = selected_category
    category_name = st.selectbox(
        t("品类") + " *",
        category_names,
        key=category_key,
    )
    category = department_categories[
        department_categories["name"] == category_name
    ].iloc[0].to_dict()
    specification_label = {
        "size": t("尺码"), "model": t("型号"), "none": t("无规格")
    }[category["specification_type"]]
    st.caption(
        t("新 SKU 说明").format(
            department=department["code"],
            specification=specification_label,
        )
    )

    active_brands = brands[
        brands.get("is_active", False) == True  # noqa: E712
    ]
    brand_options = ["", *active_brands.get("name", []).tolist()]
    active_materials = materials_for_category(materials, category["id"])
    material_options = active_materials.get("name", []).tolist()
    if not material_options:
        st.info(t("请先在“新增 SKU 选项”中新增材质。"))
        return
    version = st.session_state.get("self_service_sku_version", 0)
    if category["name"] == "黑白短袖":
        edited = _render_black_white_skus(
            brand_options, material_options, department["id"], version
        )
    else:
        edited = _render_custom_skus(
            category, specification_label, brand_options, material_options,
            department["id"], version,
        )
    if not st.button(t("保存新增 SKU"), width="stretch"):
        return
    try:
        created, skipped = create_skus(
            supabase,
            department,
            category,
            edited,
            active_brands,
            get_current_operator_name(),
            materials=active_materials,
        )
    except Exception as error:
        st.error(f"{t('新增 SKU 失败')}：{error}")
        return
    if not created:
        st.warning(t("没有可保存的新 SKU"))
        return
    message = t("已新增 SKU").format(count=created)
    if skipped:
        message += t("跳过重复 SKU").format(count=skipped)
    st.session_state["inventory_saved_message"] = message
    st.session_state["self_service_sku_version"] = version + 1
    st.rerun()


def materials_for_category(materials, category_id):
    source = pd.DataFrame(materials)
    if source.empty:
        return source
    return source[
        (source["is_active"] == True)  # noqa: E712
        & (source["category_id"] == category_id)
    ].reset_index(drop=True)


def build_black_white_sku_rows(brand, material):
    return pd.DataFrame([
        {
            "SKU 名称": "", "品牌": brand, "材质": material,
            "颜色": color, "规格": size, "单位": "件",
        }
        for color in ["白", "黑"]
        for size in SIZE_COLUMNS
    ])


def _render_black_white_skus(
    brand_options, material_options, department_id, version
):
    st.info(t("黑白短袖会自动生成黑、白两色及全部标准尺码，无需逐项填写。"))
    brand_col, material_col = st.columns(2)
    brand = brand_col.selectbox(
        t("品牌"), brand_options,
        key=f"black_white_brand_{department_id}_{version}",
    )
    material = material_col.selectbox(
        t("材质"), material_options,
        key=f"black_white_material_{department_id}_{version}",
    )
    preview = pd.DataFrame([
        {"颜色": color, **{size: "✓" for size in SIZE_COLUMNS}}
        for color in ["白", "黑"]
    ])
    st.caption(t("将自动新增以下颜色和尺码"))
    st.dataframe(preview, hide_index=True, width="stretch")
    return build_black_white_sku_rows(brand, material)


def _render_custom_skus(
    category, specification_label, brand_options, material_options,
    department_id, version,
):
    template = pd.DataFrame([{
        "品牌": "", "材质": "", "颜色": "", "规格": "", "单位": "件",
    }])
    disabled = ["规格"] if category["specification_type"] == "none" else []
    return pd.DataFrame(st.data_editor(
        template,
        hide_index=True,
        num_rows="dynamic",
        width="stretch",
        disabled=disabled,
        column_config={
            "品牌": st.column_config.SelectboxColumn(
                t("品牌"), options=brand_options
            ),
            "材质": st.column_config.SelectboxColumn(
                t("材质"), options=material_options, required=True
            ),
            "颜色": st.column_config.TextColumn(t("颜色")),
            "规格": st.column_config.TextColumn(specification_label),
            "单位": st.column_config.TextColumn(t("单位"), required=True),
        },
        key=(
            f"self_service_skus_{department_id}_{category['id']}_{version}"
        ),
    ))
