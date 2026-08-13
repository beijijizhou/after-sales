"""Link separate inventory ledgers to one human inbound business batch."""

import re

import pandas as pd

from db.inventory.container.workflow import extract_inventory_batch_id


CONTAINER_NOTE = re.compile(r"^\s*([^｜]+柜)\s*(?:｜|$)")


def container_reference(note):
    match = CONTAINER_NOTE.search(str(note or ""))
    return match.group(1).strip() if match else ""


def attach_container_batches(supabase, rows, start_date, end_date):
    """Attach a container business identity without changing ledger batch IDs."""
    result = rows.copy()
    _ensure_columns(result)
    if result.empty:
        return result
    events = (
        supabase.table("inventory_container_events")
        .select("container_key,container_no,note,effective_date")
        .in_("event_type", ["入库", "入库后更正"])
        .gte("effective_date", start_date.isoformat())
        .lt("effective_date", end_date.isoformat())
        .execute().data or []
    )
    links = {}
    for event in events:
        batch_id = extract_inventory_batch_id(event.get("note"))
        if not batch_id:
            continue
        key = str(event.get("container_key") or "").strip()
        physical = str(event.get("container_no") or "").strip()
        links[batch_id] = (
            f"货柜:{key}",
            f"{key}｜柜号 {physical}" if physical and physical != key else key,
        )
    for index, batch_id in result["batch_id"].fillna("").astype(str).items():
        if batch_id in links:
            result.at[index, "business_batch_key"] = links[batch_id][0]
            result.at[index, "business_batch_label"] = links[batch_id][1]
    return result


def _ensure_columns(rows):
    defaults = {
        "business_batch_key": "", "business_batch_label": "",
        "inventory_domain": "生产库存", "quantity_unit": "件",
    }
    for column, default in defaults.items():
        if column not in rows:
            rows[column] = default
