from datetime import timedelta

import pandas as pd

from db.inventory.operations.adjustments import (
    apply_adjustment_rows,
    reverse_inventory_batch,
)
from db.inventory.operations.outbound_verification import (
    audit_outbound_batch,
    find_outbound_inventory_issues,
    verify_outbound_batch,
)


DAILY_OUTBOUND_REASONS = [
    "仓库每日出货",
    "每日正常出货",
    "每日出货",
    "黑白短袖出库",
]
UV_DAILY_CONSUMPTION_REASON = "Google Sheets UV每日消耗"


def load_uv_daily_consumption_total(supabase, movement_date):
    rows = (
        supabase.table("inventory_movements")
        .select("quantity_change")
        .eq("department", "UV")
        .eq("movement_date", movement_date.isoformat())
        .like("reason", f"{UV_DAILY_CONSUMPTION_REASON}｜%")
        .execute()
        .data
        or []
    )
    return sum(
        abs(int(row.get("quantity_change") or 0))
        for row in rows
        if int(row.get("quantity_change") or 0) < 0
    )


def load_daily_outbound_dates(supabase, department, start_date, end_date):
    rows = (
        supabase.table("inventory_movements")
        .select("movement_date,reason")
        .eq("department", department)
        .in_("reason", DAILY_OUTBOUND_REASONS)
        .lt("quantity_change", 0)
        .gte("movement_date", start_date.isoformat())
        .lte("movement_date", end_date.isoformat())
        .execute()
        .data
        or []
    )
    recorded_dates = set()
    for row in rows:
        parsed = pd.to_datetime(
            row.get("movement_date"), errors="coerce"
        )
        if pd.isna(parsed):
            continue
        movement_date = parsed.date()
        if is_confirmed_outbound_row(movement_date, row.get("reason")):
            recorded_dates.add(movement_date)
    try:
        versioned = (
            supabase.table("inventory_daily_outbound_batches")
            .select("movement_date")
            .eq("department", department)
            .eq("status", "active")
            .gte("movement_date", start_date.isoformat())
            .lte("movement_date", end_date.isoformat())
            .execute()
            .data
            or []
        )
        recorded_dates.update(
            pd.to_datetime(row["movement_date"]).date()
            for row in versioned
            if row.get("movement_date")
        )
    except Exception:
        pass
    return recorded_dates


def is_confirmed_outbound_row(movement_date, reason):
    return reason in DAILY_OUTBOUND_REASONS


def find_missing_outbound_dates(recorded_dates, start_date, end_date):
    day_count = (end_date - start_date).days
    expected_dates = {
        start_date + timedelta(days=offset)
        for offset in range(day_count + 1)
    }
    return sorted(expected_dates - set(recorded_dates))


def load_outbound_inventory(supabase, department, category):
    rows = (
        supabase.table("inventory_items")
        .select("brand,material,color,size,quantity")
        .eq("department", department)
        .eq("category", category)
        .eq("is_active", True)
        .execute()
        .data
        or []
    )
    return pd.DataFrame(rows)


def load_daily_outbound_batch(supabase, batch_id):
    rows = (
        supabase.table("inventory_movements")
        .select(
            "batch_id,movement_date,department,category,brand,material,"
            "color,size,quantity_change,reason"
        )
        .eq("batch_id", str(batch_id))
        .execute()
        .data
        or []
    )
    return pd.DataFrame(rows)


def build_daily_outbound_edit_rows(batch_df):
    if batch_df is None or batch_df.empty:
        return pd.DataFrame()
    result = batch_df.rename(columns={
        "movement_date": "日期", "brand": "品牌",
        "material": "材质", "color": "颜色", "size": "尺码",
    }).copy()
    result["日期"] = pd.to_datetime(
        result["日期"], errors="coerce"
    ).dt.date
    result["操作"] = "扣减"
    result["数量"] = pd.to_numeric(
        result["quantity_change"], errors="coerce"
    ).fillna(0).abs().astype(int)
    result["成本"] = pd.NA
    result["备注"] = "仓库每日出货"
    return result[[
        "日期", "操作", "品牌", "材质", "颜色", "尺码",
        "数量", "成本", "备注",
    ]]


def build_replacement_inventory(current_inventory, original_batch):
    inventory = current_inventory.copy()
    if inventory.empty:
        return inventory
    for column in ["brand", "material", "color", "size"]:
        inventory[column] = (
            inventory[column].fillna("").astype(str).str.strip()
        )
    inventory["size"] = inventory["size"].str.upper()
    inventory["quantity"] = pd.to_numeric(
        inventory["quantity"], errors="coerce"
    ).fillna(0).astype(int)
    original = build_daily_outbound_edit_rows(original_batch)
    for row in original.to_dict("records"):
        matches = (
            (inventory["brand"] == str(row["品牌"]).strip())
            & (inventory["material"] == str(row["材质"]).strip())
            & (inventory["color"] == str(row["颜色"]).strip())
            & (inventory["size"] == str(row["尺码"]).strip().upper())
        )
        inventory.loc[matches, "quantity"] += int(row["数量"])
    return inventory


def replace_daily_outbound_batch(
    supabase, original_batch_id, department, category,
    original_batch_df, replacement_df, created_by,
):
    original_rows = build_daily_outbound_edit_rows(original_batch_df)
    reverse_inventory_batch(
        supabase, original_batch_id, department, category, created_by
    )
    try:
        replacement_batch_id = apply_adjustment_rows(
            supabase, department, category, replacement_df,
            created_by, source_type="daily_outbound",
        )
    except Exception as replacement_error:
        try:
            apply_adjustment_rows(
                supabase, department, category, original_rows,
                created_by, source_type="daily_outbound",
            )
        except Exception as restore_error:
            raise RuntimeError(
                "修正版保存失败，且原数据自动恢复失败："
                f"{restore_error}"
            ) from replacement_error
        raise RuntimeError(
            "修正版保存失败，原出库数据已自动恢复。"
        ) from replacement_error
    return replacement_batch_id
