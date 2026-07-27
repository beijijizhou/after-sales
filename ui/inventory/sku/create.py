import pandas as pd
import streamlit as st

from db.inventory.master_data import create_skus
from ui.inventory.i18n import t
from utils.auth import get_current_operator_name


def render_create_skus(
    supabase, department, categories, brands
):
    st.subheader(t("新增 SKU"))
    department_categories = categories[
        (categories["department_id"] == department["id"])
        & (categories["is_active"] == True)  # noqa: E712
    ]
    if department_categories.empty:
        st.info(t("当前部门还没有品类，请先在“基础资料”中新增品类。"))
        return

    category_names = department_categories["name"].tolist()
    category_name = st.selectbox(t("品类") + " *", category_names)
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
    version = st.session_state.get("self_service_sku_version", 0)
    template = pd.DataFrame([{
        "SKU 名称": "", "品牌": "", "材质": "",
        "颜色": "", "规格": "", "单位": "件",
    }])
    disabled = ["规格"] if category["specification_type"] == "none" else []
    edited = pd.DataFrame(st.data_editor(
        template,
        hide_index=True,
        num_rows="dynamic",
        width="stretch",
        disabled=disabled,
        column_config={
            "SKU 名称": st.column_config.TextColumn(
                t("SKU 名称"), help=t("SKU 名称可留空说明")
            ),
            "品牌": st.column_config.SelectboxColumn(
                t("品牌"), options=brand_options
            ),
            "材质": st.column_config.TextColumn(t("材质")),
            "颜色": st.column_config.TextColumn(t("颜色")),
            "规格": st.column_config.TextColumn(specification_label),
            "单位": st.column_config.TextColumn(t("单位"), required=True),
        },
        key=f"self_service_skus_{department['id']}_{version}",
    ))
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
