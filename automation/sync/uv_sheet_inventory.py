from dataclasses import dataclass
from datetime import date
import re
from uuid import NAMESPACE_URL, uuid5

import pandas as pd

from db.inventory.operations.adjustments import apply_adjustment_rows


DATE_TAB_PATTERN = re.compile(r"^\d{4}$")


@dataclass(frozen=True)
class InventorySku:
    department: str
    category: str
    brand: str
    material: str
    color: str
    size: str


def sync_product_from_google_sheet(
    sheets, supabase, spreadsheet_id, product_code, sku,
    start_date, end_date, created_by="system", summary_range="P16:Q40",
    range_changes=None,
):
    daily_usage = load_daily_product_usage(
        sheets,
        spreadsheet_id,
        product_code,
        start_date,
        end_date,
        summary_range,
        range_changes,
    )
    imported, skipped = sync_usage_to_inventory(
        supabase,
        sku,
        daily_usage,
        created_by=created_by,
        reason_product_code=product_code,
    )
    return {
        "daily_usage": daily_usage,
        "imported": imported,
        "skipped": skipped,
        "total_usage": sum(daily_usage.values()),
    }


def load_daily_product_usage(
    sheets, spreadsheet_id, product_code, start_date, end_date,
    summary_range="P16:Q40", range_changes=None,
):
    tabs = [
        item["title"]
        for item in sheets.list_sheets(spreadsheet_id)
        if DATE_TAB_PATTERN.fullmatch(item["title"])
        and start_date <= _tab_date(item["title"], start_date.year) <= end_date
    ]
    requested = [
        f"'{tab}'!{_summary_range_for_date(
            _tab_date(tab, start_date.year), summary_range, range_changes
        )}"
        for tab in tabs
    ]
    values_by_range = sheets.batch_get_values(spreadsheet_id, requested)
    result = {}
    for tab, cell_range in zip(tabs, requested):
        values = _range_values(values_by_range, tab, cell_range)
        quantity = _find_product_quantity(values, product_code)
        if quantity > 0:
            result[_tab_date(tab, start_date.year)] = quantity
    return dict(sorted(result.items()))


def load_daily_summary(
    sheets, spreadsheet_id, movement_date,
    summary_range="P16:Q40", range_changes=None,
):
    cell_range = _summary_range_for_date(
        movement_date, summary_range, range_changes
    )
    tab = movement_date.strftime("%m%d")
    requested = f"'{tab}'!{cell_range}"
    values = _range_values(
        sheets.batch_get_values(spreadsheet_id, [requested]),
        tab,
        requested,
    )
    result = {}
    for row in values:
        if len(row) < 2:
            continue
        product = str(row[0] or "").strip()
        if not product or product in {"材质", "总计"}:
            continue
        quantity = int(float(row[1] or 0))
        if quantity > 0:
            result[product] = quantity
    return result


def sync_usage_to_inventory(
    supabase, sku, daily_usage, created_by="system",
    reason_product_code="", reason_prefix="Google Sheets UV每日消耗",
    batch_id=None,
):
    imported = {}
    skipped = {}
    for movement_date, quantity in sorted(daily_usage.items()):
        reason = (
            f"{reason_prefix}｜{movement_date.isoformat()}｜"
            f"{reason_product_code or sku.size}"
        )
        existing = _existing_usage(
            supabase, sku, movement_date, reason_prefix
        )
        if existing:
            if existing != quantity:
                raise ValueError(
                    f"{movement_date} 已扣 {existing}，表格为 {quantity}"
                )
            skipped[movement_date] = existing
            continue
        row = pd.DataFrame([{
            "日期": movement_date,
            "操作": "扣减",
            "品牌": sku.brand,
            "材质": sku.material,
            "颜色": sku.color,
            "尺码": sku.size,
            "数量": quantity,
            "成本": pd.NA,
            "备注": reason,
        }])
        apply_adjustment_rows(
            supabase,
            sku.department,
            sku.category,
            row,
            created_by=created_by,
            source_type="bulk",
            batch_id=str(batch_id or uuid5(
                NAMESPACE_URL,
                f"{sku.department}-{sku.category}-{reason}",
            )),
        )
        imported[movement_date] = quantity
    return imported, skipped


def _tab_date(tab, year):
    return date(year, int(tab[:2]), int(tab[2:]))


def _find_product_quantity(values, product_code):
    target = product_code.strip().casefold()
    for row in values:
        if not row:
            continue
        label = str(row[0] or "").strip().casefold()
        if label == target:
            return int(float(row[1] or 0)) if len(row) > 1 else 0
    return 0


def _summary_range_for_date(
    movement_date, default_range, range_changes
):
    selected = default_range
    for effective_date, cell_range in sorted(range_changes or []):
        if movement_date >= effective_date:
            selected = cell_range
    return selected


def _range_values(values_by_range, tab, requested_range):
    if requested_range in values_by_range:
        return values_by_range[requested_range]
    suffix = requested_range.split("!", 1)[1]
    for returned_range, values in values_by_range.items():
        if returned_range.strip("'").startswith(f"{tab}'!") or (
            returned_range.endswith(suffix) and tab in returned_range
        ):
            return values
    return []


def _existing_usage(supabase, sku, movement_date, reason_prefix):
    rows = (
        supabase.table("inventory_movements")
        .select("quantity_change")
        .eq("department", sku.department)
        .eq("category", sku.category)
        .eq("brand", sku.brand)
        .eq("material", sku.material)
        .eq("color", sku.color)
        .eq("size", sku.size)
        .eq("movement_date", movement_date.isoformat())
        .like(
            "reason",
            f"{reason_prefix}｜{movement_date.isoformat()}%",
        )
        .execute()
        .data
        or []
    )
    return sum(abs(int(row["quantity_change"])) for row in rows)


def existing_usage(
    supabase, sku, movement_date,
    reason_prefix="Google Sheets UV每日消耗",
):
    return _existing_usage(
        supabase, sku, movement_date, reason_prefix
    )
