"""SKU import, inventory and master-data operation history."""

import pandas as pd
import streamlit as st

from ui.inventory.history.core.batches import add_sku_batch_key
from ui.inventory.history.import_tables import render_sku_import_table
from ui.inventory.history.sku_history_helpers import (
    change_operation,
    changed_fields,
    date_text,
    display_number,
    filter_exact_sku,
    movement_operation,
    movement_source,
    new_york_time,
    optional_int,
    signed,
    snapshot_matches,
)
from ui.inventory.i18n import t


def render_selected_sku_import(rows, selected_batch, visible_sizes=None):
    rows = add_sku_batch_key(rows)
    render_sku_import_table(
        rows[rows["batch_key"] == selected_batch], visible_sizes
    )


def render_sku_operation_history(
    inventory_df, history_data, visible_sizes=None, sku_change_log=None,
):
    st.subheader(t("SKU 操作历史"))
    st.caption(t("选择一个完整 SKU，查看它的全部库存操作时间线。"))
    identity = ["category", "brand", "material", "color", "size"]
    if inventory_df.empty or not set(identity).issubset(inventory_df.columns):
        st.info(t("暂无相关记录"))
        return
    skus = inventory_df[identity].fillna("").astype(str).drop_duplicates()
    if len(skus) > 1:
        st.info(
            f"上方筛选条件当前匹配 {len(skus):,} 个 SKU；"
            "请继续使用上方筛选器收窄到一个 SKU。"
        )
        return
    selected = skus.iloc[0].to_dict()
    selected_row = inventory_df.copy()
    for column, value in selected.items():
        selected_row = selected_row[
            selected_row[column].fillna("").astype(str) == value
        ]
    if not selected_row.empty:
        status = "启用" if bool(selected_row.iloc[0].get("is_active", True)) else "停用"
        quantity = int(selected_row.iloc[0].get("quantity") or 0)
        st.caption(f"当前状态：{status}｜当前库存：{quantity:,}")
    movements, imports, _ = history_data
    movements = filter_exact_sku(movements, selected)
    imports = filter_exact_sku(imports, selected)
    timeline = build_sku_operation_timeline(
        movements, imports, sku_change_log, selected
    )
    st.subheader("SKU 完整操作日志")
    st.caption(
        "按发生时间倒序展示库存增减、库存设置、调拨、导入，以及 "
        "SKU 资料和启用状态修改。"
    )
    if timeline.empty:
        st.info(t("暂无相关记录"))
    else:
        st.dataframe(timeline, hide_index=True, width="stretch")


def build_sku_operation_timeline(movements, imports, change_log, selected):
    """Build one chronological, user-reviewable event log for an exact SKU."""
    rows = []
    for record in pd.DataFrame(movements).to_dict("records"):
        change = int(record.get("quantity_change") or 0)
        after = optional_int(record.get("quantity_after"))
        before = after - change if after is not None else None
        reason = str(record.get("reason") or "").strip()
        rows.append({
            "操作时间（纽约）": new_york_time(record.get("created_at")),
            "业务日期": date_text(record.get("movement_date")),
            "操作": movement_operation(change, reason),
            "库存变动": signed(change),
            "操作前库存": display_number(before),
            "操作后库存": display_number(after),
            "来源/内容": movement_source(record, reason),
            "操作人": str(record.get("created_by") or "system"),
        })
    for record in pd.DataFrame(imports).to_dict("records"):
        quantity = int(record.get("initial_quantity") or 0)
        rows.append({
            "操作时间（纽约）": new_york_time(record.get("created_at")),
            "业务日期": date_text(record.get("import_date")),
            "操作": "新增 / 导入 SKU",
            "库存变动": signed(quantity),
            "操作前库存": "—",
            "操作后库存": "—",
            "来源/内容": "SKU 导入记录",
            "操作人": "system",
        })
    master_rows = _sku_master_change_rows(change_log, selected)
    rows.extend(master_rows)
    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    result = result.sort_values(
        "操作时间（纽约）", ascending=False, kind="stable"
    ).reset_index(drop=True)
    legacy_gap = _legacy_status_audit_gap(change_log, selected)
    if legacy_gap:
        result = pd.concat(
            [result, pd.DataFrame([legacy_gap])], ignore_index=True
        )
    return result


def build_sku_master_change_table(change_log, selected):
    rows = _sku_master_change_rows(change_log, selected)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).rename(columns={
        "来源/内容": "变更内容",
    })[["操作时间（纽约）", "操作", "变更内容", "操作人"]]


def _sku_master_change_rows(change_log, selected):
    rows = []
    for record in pd.DataFrame(change_log).to_dict("records"):
        old = record.get("old_identity") or {}
        new = record.get("new_identity") or {}
        if not (
            snapshot_matches(old, selected)
            or snapshot_matches(new, selected)
        ):
            continue
        changed = changed_fields(old, new)
        rows.append({
            "操作时间（纽约）": new_york_time(record.get("changed_at")),
            "业务日期": date_text(record.get("changed_at")),
            "操作": change_operation(old, new, changed),
            "库存变动": "0",
            "操作前库存": "—",
            "操作后库存": "—",
            "来源/内容": "；".join(changed) or "资料更新",
            "操作人": str(record.get("changed_by") or "system"),
        })
    return rows


def _legacy_status_audit_gap(change_log, selected):
    """Expose a pre-audit inactive state without inventing actor or time."""
    matching = []
    for record in pd.DataFrame(change_log).to_dict("records"):
        old = record.get("old_identity") or {}
        new = record.get("new_identity") or {}
        if snapshot_matches(old, selected) or snapshot_matches(new, selected):
            matching.append(record)
    if not matching:
        return None
    matching.sort(key=lambda row: str(row.get("changed_at") or ""))
    first_old = matching[0].get("old_identity") or {}
    if first_old.get("is_active") is not False:
        return None
    return {
        "操作时间（纽约）": "历史时间未记录",
        "业务日期": "—",
        "操作": "历史停用",
        "库存变动": "0",
        "操作前库存": "—",
        "操作后库存": "—",
        "来源/内容": "该 SKU 在启用审计功能前已经停用；旧系统未保存操作时间和操作人",
        "操作人": "未记录（旧版无审计）",
    }
