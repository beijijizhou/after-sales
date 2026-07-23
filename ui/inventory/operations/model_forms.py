from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.inventory import apply_adjustment_rows
from db.inventory.sku import apply_sku_rows
from ui.inventory.i18n import t
from utils.auth import get_current_operator_name, has_permission


def render_model_adjust_form(supabase, department, category, inventory_df):
    st.subheader(t("手动库存调整"))
    version = st.session_state.get("model_adjustment_version", 0)
    today = datetime.now(ZoneInfo("America/New_York")).date()
    action = st.radio(
        t("操作"), ["增加", "扣减"], horizontal=True,
        format_func=t, key="model_adjustment_action",
    )
    source_type = "bulk"
    if action == "增加":
        source = st.radio(
            t("库存来源"), ["大货", "临时调货"], horizontal=True,
            format_func=t, key="model_adjustment_source",
        )
        source_type = "transfer" if source == "临时调货" else "bulk"

    options = _model_options(inventory_df)
    template = pd.DataFrame([{
        "日期": today, "品牌": options["品牌"][0],
        "材质": options["材质"][0], "颜色": options["颜色"][0],
        "型号": options["型号"][0], "数量": 0, "备注": "",
    }])
    show_cost = has_permission("can_view_cost") and action == "增加"
    if show_cost:
        template["成本"] = None
    columns = {
        "日期": st.column_config.DateColumn(t("日期"), required=True),
        "品牌": st.column_config.SelectboxColumn(t("品牌"), options=options["品牌"]),
        "材质": st.column_config.SelectboxColumn(t("材质"), options=options["材质"], required=True),
        "颜色": st.column_config.SelectboxColumn(t("颜色"), options=options["颜色"], required=True),
        "型号": st.column_config.SelectboxColumn(t("型号"), options=options["型号"], required=True),
        "数量": st.column_config.NumberColumn(t("数量"), min_value=0, step=1, required=True),
        "备注": st.column_config.TextColumn(t("备注")),
    }
    if show_cost:
        columns["成本"] = st.column_config.NumberColumn(
            t("成本"), min_value=0.0, step=0.0001, format="%.4f"
        )
    edited = pd.DataFrame(st.data_editor(
        template, hide_index=True, num_rows="dynamic", width="stretch",
        column_config=columns, key=f"model_adjustment_{version}",
    ))
    total = pd.to_numeric(edited["数量"], errors="coerce").fillna(0).sum()
    st.metric(t("当前编辑总件数"), f"{int(total):,}")
    if not st.button(t("保存手动库存调整"), width="stretch"):
        return

    rows = _normalize_model_rows(edited, action)
    if rows.empty:
        st.warning(t("请先填写有效库存调整"))
        return
    apply_adjustment_rows(
        supabase, department, category, rows,
        get_current_operator_name(), source_type,
    )
    st.session_state["inventory_saved_message"] = t(
        "已保存库存调整"
    ).format(count=len(rows))
    st.session_state["model_adjustment_version"] = version + 1
    st.rerun()


def render_model_sku_form(supabase, department, category):
    st.subheader(t("新增 SKU"))
    version = st.session_state.get("model_sku_version", 0)
    today = datetime.now(ZoneInfo("America/New_York")).date()
    template = pd.DataFrame([{
        "日期": today, "品牌": "", "材质": "", "颜色": "白",
        "型号": "", "初始库存": 0,
    }])
    if has_permission("can_view_cost"):
        template["成本"] = None
    columns = {
        "日期": st.column_config.DateColumn(t("日期"), required=True),
        "品牌": st.column_config.TextColumn(t("品牌")),
        "材质": st.column_config.TextColumn(t("材质"), required=True),
        "颜色": st.column_config.TextColumn(t("颜色"), required=True),
        "型号": st.column_config.TextColumn(t("型号"), required=True),
        "初始库存": st.column_config.NumberColumn(
            t("初始库存"), min_value=0, step=1, required=True
        ),
    }
    if "成本" in template.columns:
        columns["成本"] = st.column_config.NumberColumn(
            t("成本"), min_value=0.0, step=0.0001, format="%.4f"
        )
    edited = pd.DataFrame(st.data_editor(
        template, hide_index=True, num_rows="dynamic", width="stretch",
        column_config=columns, key=f"model_sku_{version}",
    ))
    if not st.button(t("保存新增 SKU"), width="stretch"):
        return
    rows = _normalize_model_skus(edited)
    if rows.empty:
        st.warning(t("请先填写有效 SKU"))
        return
    apply_sku_rows(supabase, department, category, rows)
    st.session_state["inventory_saved_message"] = t(
        "已保存新 SKU"
    ).format(count=len(rows))
    st.session_state["model_sku_version"] = version + 1
    st.rerun()


def _model_options(inventory_df):
    defaults = {"品牌": [""], "材质": [""], "颜色": ["白"], "型号": [""]}
    for column in defaults:
        values = sorted({
            str(value).strip() for value in inventory_df.get(column, [])
            if pd.notna(value) and str(value).strip()
        })
        if column == "品牌":
            values = ["", *values]
        defaults[column] = values or defaults[column]
    return defaults


def _normalize_model_rows(df, action):
    result = df.rename(columns={"型号": "尺码"}).copy()
    result["操作"] = action
    result["数量"] = pd.to_numeric(result["数量"], errors="coerce").fillna(0).astype(int)
    if "成本" not in result.columns:
        result["成本"] = pd.NA
    return result[
        (result["材质"].fillna("").str.strip() != "")
        & (result["颜色"].fillna("").str.strip() != "")
        & (result["尺码"].fillna("").str.strip() != "")
        & (result["数量"] > 0)
    ][["日期", "操作", "品牌", "材质", "颜色", "尺码", "数量", "成本", "备注"]]


def _normalize_model_skus(df):
    result = df.rename(columns={"型号": "尺码"}).copy()
    result["初始库存"] = pd.to_numeric(
        result["初始库存"], errors="coerce"
    ).fillna(0).astype(int)
    if "成本" not in result.columns:
        result["成本"] = 0
    return result[
        (result["材质"].fillna("").str.strip() != "")
        & (result["颜色"].fillna("").str.strip() != "")
        & (result["尺码"].fillna("").str.strip() != "")
    ][["日期", "品牌", "材质", "颜色", "尺码", "成本", "初始库存"]]
