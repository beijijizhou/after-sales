from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.consumables import apply_consumable_batch
from ui.consumables.operations.entry import (
    _build_sku_labels,
    _normalize_entry_rows,
)
from ui.consumables.units import boxes_to_base, package_size, to_boxes
from utils.auth import get_current_operator_name


NY_TIMEZONE = ZoneInfo("America/New_York")


def render_daily_issue_table(supabase, department_code, items_df, can_edit):
    st.subheader("每日耗材扣减")
    st.caption(
        "只填写今天领用的箱数；系统按每箱数量自动换算库存扣减。"
    )
    active = _active_items(items_df, can_edit)
    if active is None:
        return
    missing_package = active[
        active["package_unit"].fillna("").astype(str).str.strip().ne("箱")
        | pd.to_numeric(
            active["units_per_package"], errors="coerce"
        ).fillna(0).le(0)
    ]
    if not missing_package.empty:
        names = "、".join(missing_package["name"].astype(str))
        st.error(f"以下耗材尚未设置每箱数量：{names}")
        st.info("请先在“SKU 管理 → 现有 SKU”中设置包装单位为箱。")
        return
    labels, label_to_row = _build_sku_labels(active)
    version = st.session_state.get("consumable_issue_version", 0)
    template = build_daily_issue_template(label_to_row)
    edited = st.data_editor(
        template,
        width="stretch",
        hide_index=True,
        key=f"daily_consumable_issue_{department_code}_{version}",
        disabled=["耗材 SKU", "当前库存（箱）", "每箱数量"],
        column_config={
            "当前库存（箱）": st.column_config.NumberColumn(format="%.2f"),
            "每箱数量": st.column_config.NumberColumn(
                min_value=1.0, format="%.4f"
            ),
            "今日领用（箱）": st.column_config.NumberColumn(
                min_value=0, step=1, format="%d"
            ),
        },
    )
    normalized = edited.rename(columns={"今日领用（箱）": "数量"})
    normalized["录入方式"] = "整包装"
    try:
        rows, preview = _normalize_entry_rows(
            normalized, label_to_row, include_cost=False
        )
    except ValueError as error:
        st.error(str(error))
        rows, preview = [], pd.DataFrame()
    _render_preview(preview, "实际扣减预览")
    movement_date = st.date_input(
        "领用日期",
        value=datetime.now(NY_TIMEZONE).date(),
        key="daily_consumable_issue_date",
    )
    confirmed = st.checkbox(
        "我已核对领用日期、耗材 SKU 和箱数",
        key="confirm_daily_consumable_issue",
    )
    if st.button(
        "确认今日扣减",
        type="primary",
        width="stretch",
        disabled=not rows or not confirmed,
    ):
        _save_batch(
            supabase, department_code, "issue", movement_date, rows,
            "每日耗材领用", "consumable_issue_version",
        )


def build_daily_issue_template(label_to_row):
    return pd.DataFrame([
        {
            "耗材 SKU": label,
            "当前库存（箱）": (
                float(item["current_quantity"])
                / float(item["units_per_package"])
            ),
            "每箱数量": float(item["units_per_package"]),
            "今日领用（箱）": 0,
            "备注": "",
        }
        for label, item in label_to_row.items()
    ])


def render_inventory_initialization(
    supabase, department_code, items_df, can_edit, show_cost
):
    st.subheader("耗材库存初始化")
    st.caption("填写目标库存；系统只记录目标库存与当前库存之间的差额。")
    active = _active_items(items_df, can_edit)
    if active is None:
        return
    labels, label_to_row = _build_sku_labels(active)
    missing = active[active.apply(package_size, axis=1).isna()]
    if not missing.empty:
        st.error(
            "以下耗材尚未设置每箱数量："
            + "、".join(missing["name"].astype(str))
        )
        return
    columns = ["耗材 SKU", "当前库存（箱）", "目标库存（箱）", "备注"]
    if show_cost:
        columns.insert(3, "单位成本")
    template = pd.DataFrame([
        {
            "耗材 SKU": label,
            "当前库存（箱）": to_boxes(item["current_quantity"], item),
            "目标库存（箱）": to_boxes(item["current_quantity"], item),
            "单位成本": None,
            "备注": "",
        }
        for label, item in label_to_row.items()
    ])[columns]
    edited = st.data_editor(
        template,
        width="stretch",
        hide_index=True,
        key=f"consumable_initialization_{department_code}",
        disabled=["耗材 SKU", "当前库存（箱）"],
        column_config={
            "当前库存（箱）": st.column_config.NumberColumn(format="%.2f"),
            "目标库存（箱）": st.column_config.NumberColumn(
                min_value=0.0, step=1, format="%.2f"
            ),
            "单位成本": st.column_config.NumberColumn(
                min_value=0.0, step=0.0001, format="$%.4f"
            ),
        },
    )
    rows, preview = _normalize_initialization(
        edited, label_to_row, show_cost
    )
    _render_preview(preview, "初始化变动预览")
    movement_date = st.date_input(
        "盘点日期",
        value=datetime.now(NY_TIMEZONE).date(),
        key="consumable_initialization_date",
    )
    confirmed = st.checkbox(
        "我已核对目标库存",
        key="confirm_consumable_initialization",
    )
    if st.button(
        "保存初始化库存",
        type="primary",
        width="stretch",
        disabled=not rows or not confirmed,
    ):
        _save_batch(
            supabase, department_code, "adjustment", movement_date, rows,
            "耗材库存初始化", None,
        )


def _normalize_initialization(edited, label_to_row, include_cost):
    rows, preview = [], []
    for row in edited.to_dict("records"):
        label = row["耗材 SKU"]
        item = label_to_row[label]
        current_boxes = to_boxes(item["current_quantity"], item)
        target_boxes = pd.to_numeric(
            row.get("目标库存（箱）", row.get("目标库存")), errors="coerce"
        )
        if current_boxes is None or pd.isna(target_boxes) or target_boxes < 0:
            continue
        target = boxes_to_base(target_boxes, item)
        difference = float(target) - float(item["current_quantity"])
        if abs(difference) < 0.00005:
            continue
        record = {
            "item_id": item["id"],
            "quantity": difference,
            "note": row.get("备注") or "",
        }
        cost = pd.to_numeric(row.get("单位成本"), errors="coerce")
        if include_cost and not pd.isna(cost):
            record["unit_cost"] = float(cost)
        rows.append(record)
        preview.append({
            "耗材 SKU": label,
            "当前库存（箱）": current_boxes,
            "目标库存（箱）": float(target_boxes),
            "库存差额（箱）": float(target_boxes) - current_boxes,
            **({"单位成本": record.get("unit_cost")} if include_cost else {}),
        })
    return rows, pd.DataFrame(preview)


def _active_items(items_df, can_edit):
    if not can_edit:
        st.info("当前账号只有查看权限，不能修改耗材库存。")
        return None
    active = items_df[items_df["is_active"] == True].copy()
    if active.empty:
        st.warning("请先在“SKU 管理”中建立并启用耗材 SKU。")
        return None
    return active


def _render_preview(preview, title):
    if preview.empty:
        return
    st.caption(title)
    st.dataframe(preview, width="stretch", hide_index=True)


def _save_batch(
    supabase, department_code, movement_type, movement_date, rows,
    note, version_key,
):
    try:
        apply_consumable_batch(
            supabase, department_code, movement_type, movement_date,
            rows, get_current_operator_name(), note,
        )
    except Exception as error:
        st.error(f"耗材库存保存失败：{error}")
        return
    if version_key:
        st.session_state[version_key] = st.session_state.get(version_key, 0) + 1
    st.session_state["consumable_saved_message"] = "耗材库存已更新。"
    st.rerun()
