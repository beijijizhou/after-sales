import pandas as pd
import streamlit as st

from utils.image_tools.compatibility import (
    build_dieline_compatibility_groups,
    build_full_report_rows,
    build_material_family_details,
    find_compatibility_group,
)
from utils.image_tools.templates import (
    get_dieline_materials,
    get_dieline_models,
)


@st.cache_data(show_spinner=False)
def _load_compatibility_groups():
    return build_dieline_compatibility_groups()


def render_phone_case_parameters():
    groups = _load_compatibility_groups()
    overview_tab, analysis_tab = st.tabs(
        ["共用机型", "批量分析与查询"]
    )
    with overview_tab:
        _render_boss_overview(groups)
    with analysis_tab:
        _render_analysis_tools(groups)


def _render_boss_overview(groups):
    details = build_material_family_details(groups)
    st.subheader("刀模共用结论")
    conclusion_lines = [
        _build_shared_conclusion(family)
        for family in details["shared_families"]
    ]
    conclusion_lines.extend(
        (
            f"- **{material['material']}**："
            f"**{len(material['models'])} 个型号全部不共享**"
        )
        for material in details["independent_materials"]
    )
    st.success("\n".join(conclusion_lines))

    category_rows = _build_category_rows(details)
    categories = list(category_rows)
    selected_category = st.selectbox(
        "查看分类",
        ["全部分类", *categories],
        key="boss_dieline_category",
    )
    rows = (
        [
            row
            for category in categories
            for row in category_rows[category]
        ]
        if selected_category == "全部分类"
        else category_rows[selected_category]
    )
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        height=_table_height(rows),
    )
    st.caption(
        "结论仅代表套图刀模可共用，不代表实物手机壳库存可以互换。"
    )


def _render_analysis_tools(groups):
    st.subheader("批量刀模分析")
    st.caption(
        "自动分析当前刀模库的目标尺寸、外轮廓和摄像头开孔。"
    )
    if st.button(
        "重新分析全部刀模",
        type="primary",
        width="stretch",
    ):
        _load_compatibility_groups.clear()
        st.session_state["dieline_analysis_complete"] = True
        st.rerun()

    compatible_groups = [
        group for group in groups if len(group["members"]) > 1
    ]
    total_templates = sum(len(group["members"]) for group in groups)
    compatible_templates = sum(
        len(group["members"]) for group in compatible_groups
    )
    independent_groups = [
        group for group in groups if len(group["members"]) == 1
    ]

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("刀模数量", total_templates)
    metric2.metric("参数组", len(groups))
    metric3.metric("可互用刀模", compatible_templates)
    metric4.metric("独立机型", len(independent_groups))
    if st.session_state.pop("dieline_analysis_complete", False):
        st.success(
            f"分析完成：{total_templates} 份刀模，"
            f"{len(compatible_groups)} 个可互用参数组。"
        )
    st.download_button(
        "下载完整分析报告",
        data=pd.DataFrame(build_full_report_rows(groups)).to_csv(
            index=False,
        ).encode("utf-8-sig"),
        file_name="手机壳刀模参数分析.csv",
        mime="text/csv",
        width="stretch",
    )
    st.caption(
        "完全一致仅代表套图刀模可互用，不代表实物手机壳库存可以互换。"
    )

    st.subheader("查询单个刀模")
    material_col, model_col = st.columns(2)
    material = material_col.selectbox(
        "材质",
        get_dieline_materials(),
        key="parameter_material",
    )
    model = model_col.selectbox(
        "型号",
        get_dieline_models(material),
        key="parameter_model",
    )
    selected_group = find_compatibility_group(groups, material, model)
    _render_selected_group(selected_group, material, model)


def _render_selected_group(group, material, model):
    if group is None:
        st.warning("没有找到该刀模的参数。")
        return
    members = group["members"]
    if len(members) == 1:
        st.info("该刀模目前没有完全一致、可以互用的其他刀模。")
    else:
        st.success(
            f"{group['group_id']}：共有 {len(members)} 份刀模可互用"
        )
    rows = []
    for row in members:
        rows.append(
            {
                "当前选择": (
                    "是"
                    if row["material"] == material
                    and row["model"] == model
                    else ""
                ),
                "型号": row["model"],
                "材质": row["material"],
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def _table_height(rows):
    return min(38 * (len(rows) + 1), 840)


def _build_category_rows(details):
    category_rows = {}
    for family in details["shared_families"]:
        category = " ↔ ".join(family["materials"])
        rows = [
            {
                "分类": category,
                "结论": "可共用",
                "型号": model,
                "备注": "",
            }
            for model in family["common_models"]
        ]
        rows.extend(
            {
                "分类": category,
                "结论": "可共用",
                "型号": " ↔ ".join(models),
                "备注": "跨型号同刀模，建议确认",
            }
            for models in family["special_matches"]
        )
        category_rows[category] = rows
    for material in details["independent_materials"]:
        category = material["material"]
        category_rows[category] = [
            {
                "分类": category,
                "结论": "独立",
                "型号": model,
                "备注": "",
            }
            for model in material["models"]
        ]
    return category_rows


def _build_shared_conclusion(family):
    line = (
        f"- **{' ↔ '.join(family['materials'])}**："
        f"共同拥有的 **{len(family['common_models'])} 个同名型号"
        "全部可以共用刀模**"
    )
    remaining_parts = [
        f"{material}：{'、'.join(models)}"
        for material, models in family["remaining_by_material"].items()
        if models
    ]
    if not remaining_parts:
        return f"{line}；**没有剩余不共用型号**"
    return (
        f"{line}；未按同名对应的型号为"
        f"{'；'.join(remaining_parts)}。"
        "这些刀模存在跨型号相同，需要确认命名"
    )
