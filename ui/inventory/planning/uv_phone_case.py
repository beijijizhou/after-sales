"""Phone-case allocation UI for the UV daily source preview."""

from hashlib import sha1

import pandas as pd
import streamlit as st

from automation.sync.uv_daily_operation import (
    PHONE_CASE_PENDING_STATUS,
    build_phone_case_allocation_preview,
    phone_case_sku_key,
    phone_case_sku_label,
)
from db.inventory.core.queries import load_inventory_items
from ui.inventory.operations.system_deduction import system_deduction_comparison
from ui.operations import render_stock_change_review


def render_phone_case_allocation(supabase, phone_summary, current_date):
    if phone_summary.empty:
        st.info("今日 Google Sheets 没有手机壳消耗。")
        return phone_summary, ""
    summary = phone_summary.iloc[0]
    if summary["状态"] == "已同步":
        st.success(f"今日手机壳 {int(summary['当日消耗']):,} 件已经扣减。")
        return phone_summary.iloc[0:0].copy(), ""
    if summary["状态"] != PHONE_CASE_PENDING_STATUS:
        st.error(str(summary["状态"]))
        return phone_summary, str(summary["状态"])

    required = int(summary["当日消耗"])
    inventory = load_inventory_items(supabase, "UV", "手机壳")
    inventory = inventory[
        inventory["material"].fillna("").astype(str).str.strip().ne("")
    ].copy()
    inventory["_sku_key"] = inventory.apply(
        lambda row: phone_case_sku_key(row.to_dict()), axis=1
    )
    labels = {
        row["_sku_key"]: phone_case_sku_label(row)
        for row in inventory.to_dict("records")
    }
    selected = st.multiselect(
        "选择今天实际消耗的手机壳材质与型号",
        options=inventory["_sku_key"].tolist(),
        format_func=lambda key: labels.get(key, key),
        key=f"uv_phone_case_skus_{current_date:%Y%m%d}",
        placeholder="可搜索材质或 iPhone 型号",
    )
    selected_inventory = inventory[inventory["_sku_key"].isin(selected)]
    editor = selected_inventory[[
        "_sku_key", "material", "size", "quantity",
    ]].rename(columns={
        "material": "材质", "size": "型号", "quantity": "当前库存",
    })
    editor["本次出库"] = 0
    signature = sha1("|".join(selected).encode()).hexdigest()[:10]
    edited = pd.DataFrame(st.data_editor(
        editor,
        hide_index=True,
        width="stretch",
        disabled=["_sku_key", "材质", "型号", "当前库存"],
        column_config={
            "_sku_key": None,
            "当前库存": st.column_config.NumberColumn(format="%d"),
            "本次出库": st.column_config.NumberColumn(
                min_value=0, step=1, format="%d"
            ),
        },
        key=f"uv_phone_case_allocation_{current_date:%Y%m%d}_{signature}",
    ))
    allocations = {
        str(row["_sku_key"]): int(row["本次出库"] or 0)
        for row in edited.to_dict("records")
    }
    allocation_rows = build_phone_case_allocation_preview(
        inventory, allocations
    )
    allocated = int(allocation_rows.get(
        "预计扣减", pd.Series(dtype=float)
    ).sum())
    st.metric("Google Sheets 手机壳总消耗", f"{required:,} 件")
    st.metric("已分配到具体型号", f"{allocated:,} 件")
    if not allocation_rows.empty:
        render_stock_change_review(
            system_deduction_comparison(allocation_rows),
            action="出库",
            title="手机壳型号扣减核对",
            identity_columns=["状态", "材质", "型号"],
            extra_columns=["当日消耗"],
            unit="件",
            quantity_format="%d",
        )
    if allocated != required:
        difference = required - allocated
        message = (
            f"还需分配 {difference:,} 件"
            if difference > 0 else f"已超出表格总数 {abs(difference):,} 件"
        )
        st.warning(message)
        return allocation_rows, message
    if (allocation_rows["状态"] == "库存不足").any():
        return allocation_rows, "存在库存不足的手机壳型号"
    return allocation_rows, ""
