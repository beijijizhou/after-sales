from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from db.inventory import (
    SIZE_COLUMNS,
    apply_adjustment_rows,
    build_wide_adjustment_template,
    normalize_adjustment_rows,
)
from db.inventory.sku import (
    apply_sku_rows,
    build_sku_template,
    normalize_sku_rows,
    parse_sku_file,
)
from utils.auth import get_current_operator_name, has_permission
from ui.inventory.i18n import get_language, t


def render_adjust_form(supabase, department, category, inventory_df):
    st.subheader(t("手动库存调整"))

    current_date = datetime.now(ZoneInfo("America/New_York")).date()
    form_version = st.session_state.get("manual_adjustment_editor_version", 0)
    brand_values = sorted(inventory_df["品牌"].unique().tolist()) if not inventory_df.empty else []
    brands = list(dict.fromkeys(["", *brand_values]))
    materials = sorted(inventory_df["材质"].unique().tolist()) if not inventory_df.empty else ["180g"]
    colors = sorted(inventory_df["颜色"].unique().tolist()) if not inventory_df.empty else []
    default_df = build_wide_adjustment_template()
    default_df.loc[0, "日期"] = current_date
    default_df.loc[0, "材质"] = "180g"
    show_cost = has_permission("can_view_cost")
    if show_cost:
        default_df.insert(4, "成本", None)
    action = st.radio(
        t("操作"), ["增加", "扣减"], horizontal=True, format_func=t
    )
    adjustment_columns = {
        "日期": st.column_config.DateColumn(t("日期"), required=True),
        "品牌": st.column_config.SelectboxColumn(t("品牌"), options=brands, required=False),
        "材质": st.column_config.SelectboxColumn(t("材质"), options=materials, required=True),
        "颜色": st.column_config.SelectboxColumn(t("颜色"), options=colors, required=True),
    }
    if show_cost:
        adjustment_columns["成本"] = st.column_config.NumberColumn(t("成本"), min_value=0, step=0.01)
    for size in SIZE_COLUMNS:
        adjustment_columns[size] = st.column_config.NumberColumn(size, min_value=0, step=1)
    adjustment_columns["备注"] = st.column_config.TextColumn(t("备注"))
    edited_df = st.data_editor(
        default_df,
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        column_config=adjustment_columns,
        key=(
            f"manual_inventory_adjustments_{get_language()}_"
            f"{current_date.isoformat()}_{form_version}"
        ),
    )
    if st.button(t("保存手动库存调整"), use_container_width=True):
        try:
            edited_df["操作"] = action
            adjustment_df = normalize_adjustment_rows(edited_df)
            if adjustment_df.empty:
                st.warning(t("请先填写有效库存调整"))
                return
            if not show_cost and "成本" in adjustment_df.columns:
                adjustment_df = adjustment_df.drop(columns=["成本"])
            username = get_current_operator_name()
            apply_adjustment_rows(
                supabase, department, category, adjustment_df, username
            )
            st.session_state["inventory_saved_message"] = (
                t("已保存库存调整").format(count=len(adjustment_df))
            )
            st.session_state["manual_adjustment_editor_version"] = form_version + 1
            st.session_state.pop("inventory_history_date", None)
            st.rerun()
        except Exception as e:
            st.error(f"{t('库存更新失败')}: {e}")


def render_new_sku_form(supabase, department, category, inventory_df=None):
    st.subheader(t("新增 SKU"))
    saved_message = st.session_state.pop("new_sku_saved_message", None)
    if saved_message:
        st.success(saved_message)
    form_version = st.session_state.get("new_sku_editor_version", 0)
    can_view_cost = has_permission("can_view_cost")
    show_cost = False
    if can_view_cost:
        with st.expander(t("内部字段"), expanded=False):
            show_cost = st.checkbox(t("启用成本列"), value=True, key="show_new_sku_cost")

    template_df = build_sku_template()
    if not show_cost:
        template_df = template_df.drop(columns=["成本"])

    st.download_button(
        t("下载新增 SKU 模板"), data=template_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="新增SKU模板.csv", mime="text/csv", use_container_width=True,
    )
    uploaded_file = st.file_uploader(
        t("上传新增 SKU Excel / CSV"),
        type=["xlsx", "xls", "csv"],
        key=f"new_sku_upload_{form_version}",
    )
    if uploaded_file is not None:
        try:
            sku_df = parse_sku_file(uploaded_file)
        except Exception as e:
            st.error(f"{t('文件读取失败')}: {e}")
            return
    else:
        default_df = build_sku_template()
        default_df.loc[0, "日期"] = datetime.now(ZoneInfo("America/New_York")).date()
        default_df.loc[0, "材质"] = "180g"
        if not show_cost:
            default_df = default_df.drop(columns=["成本"])
        sku_columns = {"日期": st.column_config.DateColumn(t("日期"), required=True)}
        sku_columns["品牌"] = st.column_config.TextColumn(t("品牌"))
        sku_columns["材质"] = st.column_config.TextColumn(t("材质"), required=True)
        sku_columns["颜色"] = st.column_config.TextColumn(t("颜色"), required=True)
        if show_cost:
            sku_columns["成本"] = st.column_config.NumberColumn(t("成本"), min_value=0, step=0.01)
        for size in SIZE_COLUMNS:
            sku_columns[size] = st.column_config.NumberColumn(size, min_value=0, step=1)
        sku_df = st.data_editor(
            default_df, hide_index=True, num_rows="dynamic", use_container_width=True,
            column_config=sku_columns,
            key=f"new_inventory_skus_{get_language()}_{form_version}",
        )

    if uploaded_file is not None:
        preview_df = sku_df if show_cost or "成本" not in sku_df.columns else sku_df.drop(columns=["成本"])
        st.dataframe(preview_df, hide_index=True, use_container_width=True)
    if st.button(t("保存新增 SKU"), use_container_width=True):
        try:
            cleaned_df = normalize_sku_rows(sku_df)
            if cleaned_df.empty:
                st.warning(t("请先填写有效 SKU"))
                return
            if inventory_df is not None and not inventory_df.empty:
                existing_keys = set(zip(inventory_df["品牌"], inventory_df["材质"], inventory_df["颜色"]))
                original_count = len(cleaned_df)
                cleaned_df = cleaned_df[
                    ~cleaned_df.apply(lambda row: (row["品牌"], row["材质"], row["颜色"]) in existing_keys, axis=1)
                ]
                if cleaned_df.empty:
                    st.warning(t("重复 SKU"))
                    return
                skipped_count = original_count - len(cleaned_df)
            else:
                skipped_count = 0

            apply_sku_rows(supabase, department, category, cleaned_df)
            message = t("已保存新 SKU").format(count=len(cleaned_df))
            if skipped_count:
                message += " " + t("已跳过 SKU").format(count=skipped_count)
            st.session_state["new_sku_saved_message"] = message
            st.session_state["new_sku_editor_version"] = st.session_state.get("new_sku_editor_version", 0) + 1
            st.rerun()
        except Exception as e:
            st.error(f"{t('新增 SKU 失败')}: {e}")


def render_inventory_unit_calculator():
    st.markdown(f"#### {t('临时箱数换算')}")
    box_col, unit_col, loose_col, total_col = st.columns(4)
    box_count = box_col.number_input(
        t("箱数"), min_value=0, value=0, step=1,
        key="inventory_calculator_box_count",
    )
    units_per_box = unit_col.number_input(
        t("每箱件数"), min_value=1, value=72, step=1,
        key="inventory_calculator_units_per_box",
    )
    loose_units = loose_col.number_input(
        t("零散件数"), min_value=0, value=0, step=1,
        key="inventory_calculator_loose_units",
    )
    total_units = int(box_count * units_per_box + loose_units)
    total_col.metric(t("换算总件数"), f"{total_units:,}")
    st.caption(t("换算结果仅供填写库存调整表，不会自动修改库存。"))
