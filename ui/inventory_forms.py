from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from db.inventory import (
    SIZE_COLUMNS,
    apply_adjustment_rows,
    build_adjustment_template,
    build_wide_adjustment_template,
    normalize_adjustment_rows,
    parse_adjustment_file,
)
from db.inventory_sku import (
    apply_sku_rows,
    build_sku_template,
    normalize_sku_rows,
    parse_sku_file,
)
from utils.auth import has_permission


def render_adjust_form(supabase, department, category, inventory_df):
    st.subheader("手动库存调整")

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
    action = st.radio("操作", ["增加", "扣减"], horizontal=True)
    adjustment_columns = {
        "日期": st.column_config.DateColumn("日期", required=True),
        "品牌": st.column_config.SelectboxColumn("品牌", options=brands, required=False),
        "材质": st.column_config.SelectboxColumn("材质", options=materials, required=True),
        "颜色": st.column_config.SelectboxColumn("颜色", options=colors, required=True),
    }
    if show_cost:
        adjustment_columns["成本"] = st.column_config.NumberColumn("成本", min_value=0, step=0.01)
    for size in SIZE_COLUMNS:
        adjustment_columns[size] = st.column_config.NumberColumn(size, min_value=0, step=1)
    adjustment_columns["备注"] = st.column_config.TextColumn("备注")
    edited_df = st.data_editor(
        default_df,
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        column_config=adjustment_columns,
        key=f"manual_inventory_adjustments_{current_date.isoformat()}_{form_version}",
    )
    if st.button("保存手动库存调整", use_container_width=True):
        try:
            edited_df["操作"] = action
            adjustment_df = normalize_adjustment_rows(edited_df)
            if adjustment_df.empty:
                st.warning("请先填写有效库存调整")
                return
            if not show_cost and "成本" in adjustment_df.columns:
                adjustment_df = adjustment_df.drop(columns=["成本"])
            apply_adjustment_rows(supabase, department, category, adjustment_df)
            st.session_state["inventory_saved_message"] = (
                f"已保存 {len(adjustment_df)} 条库存调整，库存明细已刷新"
            )
            st.session_state["manual_adjustment_editor_version"] = form_version + 1
            st.session_state.pop("inventory_history_date", None)
            st.rerun()
        except Exception as e:
            st.error(f"库存更新失败：{e}")


def render_new_sku_form(supabase, department, category, inventory_df=None):
    st.subheader("新增 SKU")
    saved_message = st.session_state.pop("new_sku_saved_message", None)
    if saved_message:
        st.success(saved_message)
    form_version = st.session_state.get("new_sku_editor_version", 0)
    can_view_cost = has_permission("can_view_cost")
    show_cost = False
    if can_view_cost:
        with st.expander("内部字段", expanded=False):
            show_cost = st.checkbox("启用成本列", value=True, key="show_new_sku_cost")

    template_df = build_sku_template()
    if not show_cost:
        template_df = template_df.drop(columns=["成本"])

    st.download_button(
        "下载新增 SKU 模板", data=template_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="新增SKU模板.csv", mime="text/csv", use_container_width=True,
    )
    uploaded_file = st.file_uploader(
        "上传新增 SKU Excel / CSV",
        type=["xlsx", "xls", "csv"],
        key=f"new_sku_upload_{form_version}",
    )
    if uploaded_file is not None:
        try:
            sku_df = parse_sku_file(uploaded_file)
        except Exception as e:
            st.error(f"文件读取失败：{e}")
            return
    else:
        default_df = build_sku_template()
        default_df.loc[0, "日期"] = datetime.now(ZoneInfo("America/New_York")).date()
        default_df.loc[0, "材质"] = "180g"
        if not show_cost:
            default_df = default_df.drop(columns=["成本"])
        sku_columns = {"日期": st.column_config.DateColumn("日期", required=True)}
        sku_columns["品牌"] = st.column_config.TextColumn("品牌")
        sku_columns["材质"] = st.column_config.TextColumn("材质", required=True)
        sku_columns["颜色"] = st.column_config.TextColumn("颜色", required=True)
        if show_cost:
            sku_columns["成本"] = st.column_config.NumberColumn("成本", min_value=0, step=0.01)
        for size in SIZE_COLUMNS:
            sku_columns[size] = st.column_config.NumberColumn(size, min_value=0, step=1)
        sku_df = st.data_editor(
            default_df, hide_index=True, num_rows="dynamic", use_container_width=True,
            column_config=sku_columns,
            key=f"new_inventory_skus_{form_version}",
        )

    if uploaded_file is not None:
        preview_df = sku_df if show_cost or "成本" not in sku_df.columns else sku_df.drop(columns=["成本"])
        st.dataframe(preview_df, hide_index=True, use_container_width=True)
    if st.button("保存新增 SKU", use_container_width=True):
        try:
            cleaned_df = normalize_sku_rows(sku_df)
            if cleaned_df.empty:
                st.warning("请先填写有效 SKU")
                return
            if inventory_df is not None and not inventory_df.empty:
                existing_keys = set(zip(inventory_df["品牌"], inventory_df["材质"], inventory_df["颜色"]))
                original_count = len(cleaned_df)
                cleaned_df = cleaned_df[
                    ~cleaned_df.apply(lambda row: (row["品牌"], row["材质"], row["颜色"]) in existing_keys, axis=1)
                ]
                if cleaned_df.empty:
                    st.warning("这些品牌、材质和颜色已经存在，请不要重复新增 SKU")
                    return
                skipped_count = original_count - len(cleaned_df)
            else:
                skipped_count = 0

            apply_sku_rows(supabase, department, category, cleaned_df)
            message = f"已保存 {len(cleaned_df)} 条新 SKU，库存明细已刷新"
            if skipped_count:
                message += f"，已跳过 {skipped_count} 条已存在 SKU"
            st.session_state["new_sku_saved_message"] = message
            st.session_state["new_sku_editor_version"] = st.session_state.get("new_sku_editor_version", 0) + 1
            st.rerun()
        except Exception as e:
            st.error(f"新增 SKU 失败：{e}")


def render_excel_adjustment(supabase, department, category):
    st.subheader("Excel 库存调整")

    st.download_button(
        "下载库存调整模板",
        data=build_adjustment_template().to_csv(index=False).encode("utf-8-sig"),
        file_name="库存调整模板.csv",
        mime="text/csv",
        use_container_width=True,
    )
    uploaded_file = st.file_uploader("上传库存调整 Excel / CSV", type=["xlsx", "xls", "csv"])
    if uploaded_file is None:
        return

    try:
        adjustment_df = parse_adjustment_file(uploaded_file)
    except Exception as e:
        st.error(f"文件读取失败：{e}")
        return

    if adjustment_df.empty:
        st.warning("文件中没有有效库存调整")
        return

    st.dataframe(adjustment_df, hide_index=True, use_container_width=True)
    if st.button("确认导入库存调整", use_container_width=True):
        try:
            apply_adjustment_rows(supabase, department, category, adjustment_df)
            st.success(f"已导入 {len(adjustment_df)} 条库存调整")
            st.rerun()
        except Exception as e:
            st.error(f"导入失败：{e}")
