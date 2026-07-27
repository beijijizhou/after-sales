import streamlit as st

from db.inventory.master_data import (
    SPECIFICATION_TYPES,
    create_brand,
    create_category,
    create_department,
)
from ui.inventory.i18n import t
from utils.auth import get_current_operator_name


def render_master_data_forms(supabase, departments):
    st.subheader(t("基础资料"))
    st.caption(t("基础资料说明"))
    department_tab, category_tab, brand_tab = st.tabs([
        t("新增部门"), t("新增品类"), t("新增品牌"),
    ])
    operator = get_current_operator_name()

    with department_tab:
        with st.form("create_inventory_department"):
            code = st.text_input(t("部门代码") + " *", placeholder="DTF")
            name = st.text_input(t("部门名称") + " *")
            submitted = st.form_submit_button(
                t("保存部门"), width="stretch"
            )
        if submitted:
            _save(
                lambda: create_department(
                    supabase, code, name, operator
                ),
                t("部门已新增"),
            )

    active_departments = departments[
        departments.get("is_active", False) == True  # noqa: E712
    ]
    department_options = active_departments.to_dict("records")
    department_names = {
        f"{row['code']}｜{row['name']}": row["id"]
        for row in department_options
    }
    with category_tab:
        if not department_names:
            st.info(t("请先新增部门"))
        else:
            with st.form("create_inventory_category"):
                department_label = st.selectbox(
                    t("所属部门") + " *", list(department_names)
                )
                category_name = st.text_input(t("品类名称") + " *")
                specification_label = st.segmented_control(
                    t("规格方式") + " *",
                    list(SPECIFICATION_TYPES),
                    default="无规格",
                    format_func=t,
                )
                submitted = st.form_submit_button(
                    t("保存品类"), width="stretch"
                )
            if submitted:
                _save(
                    lambda: create_category(
                        supabase,
                        department_names[department_label],
                        category_name,
                        SPECIFICATION_TYPES[specification_label],
                        operator,
                    ),
                    t("品类已新增"),
                )

    with brand_tab:
        with st.form("create_inventory_brand"):
            brand_name = st.text_input(t("品牌名称") + " *")
            submitted = st.form_submit_button(
                t("保存品牌"), width="stretch"
            )
        if submitted:
            _save(
                lambda: create_brand(supabase, brand_name, operator),
                t("品牌已新增"),
            )


def _save(action, message):
    try:
        action()
    except Exception as error:
        if "duplicate" in str(error).lower():
            st.warning(t("这项资料已经存在"))
            return
        st.error(f"{t('保存失败')}：{error}")
        return
    st.session_state["inventory_saved_message"] = message
    st.rerun()
