"""Legacy DTF wide-table SKU creation workflow."""

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from db.inventory import SIZE_COLUMNS
from db.inventory.sku import apply_sku_rows, build_sku_template, normalize_sku_rows, parse_sku_file
from ui.inventory.i18n import get_language, t
from utils.auth import has_permission


def render_new_sku_form(supabase, department, category, inventory_df=None):
    from ui.inventory.operations.model_forms import render_model_sku_form
    if department != "DTF":
        return render_model_sku_form(supabase, department, category)
    st.subheader(t("新增 SKU"))
    message = st.session_state.pop("new_sku_saved_message", None)
    if message:
        st.success(message)
    version = st.session_state.get("new_sku_editor_version", 0)
    show_cost = False
    if has_permission("can_manage_cost"):
        with st.expander(t("内部字段"), expanded=False):
            show_cost = st.checkbox(t("启用成本列"), value=True, key="show_new_sku_cost")
    template = build_sku_template()
    if not show_cost:
        template = template.drop(columns=["成本"])
    st.download_button(t("下载新增 SKU 模板"), data=template.to_csv(index=False).encode("utf-8-sig"), file_name="新增SKU模板.csv", mime="text/csv", width="stretch")
    uploaded = st.file_uploader(t("上传新增 SKU Excel / CSV"), type=["xlsx", "xls", "csv"], key=f"new_sku_upload_{version}")
    try:
        sku_df = parse_sku_file(uploaded) if uploaded is not None else _render_editor(show_cost, version)
    except Exception as error:
        st.error(f"{t('文件读取失败')}: {error}")
        return
    if uploaded is not None:
        preview = sku_df if show_cost or "成本" not in sku_df.columns else sku_df.drop(columns=["成本"])
        st.dataframe(preview, hide_index=True, width="stretch")
    if not st.button(t("保存新增 SKU"), width="stretch"):
        return
    try:
        cleaned = normalize_sku_rows(sku_df)
        if cleaned.empty:
            st.warning(t("请先填写有效 SKU"))
            return
        cleaned, skipped = _remove_existing(cleaned, inventory_df)
        if cleaned.empty:
            st.warning(t("重复 SKU"))
            return
        apply_sku_rows(supabase, department, category, cleaned)
        message = t("已保存新 SKU").format(count=len(cleaned))
        if skipped:
            message += " " + t("已跳过 SKU").format(count=skipped)
        st.session_state["new_sku_saved_message"] = message
        st.session_state["new_sku_editor_version"] = version + 1
        st.rerun()
    except Exception as error:
        st.error(f"{t('新增 SKU 失败')}: {error}")


def _render_editor(show_cost, version):
    table = build_sku_template()
    table.loc[0, "日期"] = datetime.now(ZoneInfo("America/New_York")).date()
    table.loc[0, "材质"] = "180g"
    if not show_cost:
        table = table.drop(columns=["成本"])
    config = {"日期": st.column_config.DateColumn(t("日期"), required=True), "品牌": st.column_config.TextColumn(t("品牌")), "材质": st.column_config.TextColumn(t("材质"), required=True), "颜色": st.column_config.TextColumn(t("颜色"), required=True)}
    if show_cost:
        config["成本"] = st.column_config.NumberColumn(t("成本"), min_value=0.0, step=0.0001, format="%.4f")
    config.update({size: st.column_config.NumberColumn(size, min_value=0, step=1) for size in SIZE_COLUMNS})
    return st.data_editor(table, hide_index=True, num_rows="dynamic", width="stretch", column_config=config, key=f"new_inventory_skus_{get_language()}_{version}")


def _remove_existing(cleaned, inventory):
    if inventory is None or inventory.empty:
        return cleaned, 0
    keys = set(zip(inventory["品牌"], inventory["材质"], inventory["颜色"]))
    count = len(cleaned)
    cleaned = cleaned[~cleaned.apply(lambda row: (row["品牌"], row["材质"], row["颜色"]) in keys, axis=1)]
    return cleaned, count - len(cleaned)
