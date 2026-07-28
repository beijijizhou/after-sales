from uuid import uuid4

import pandas as pd


def apply_consumable_batch(
    supabase, department_code, movement_type, movement_date, rows,
    created_by, note="", source_file_name="",
):
    records = []
    for row in rows:
        record = {
            "item_id": row["item_id"],
            "quantity": float(row["quantity"]),
            "note": str(row.get("note") or "").strip(),
        }
        unit_cost = row.get("unit_cost")
        if unit_cost is not None and not pd.isna(unit_cost):
            record["unit_cost"] = round(float(unit_cost), 4)
        records.append(record)

    response = supabase.rpc(
        "apply_consumable_movement_batch",
        {
            "p_department_code": department_code,
            "p_movement_type": movement_type,
            "p_movement_date": movement_date.isoformat(),
            "p_rows": records,
            "p_batch_id": str(uuid4()),
            "p_created_by": created_by,
            "p_note": note or None,
            "p_source_file_name": source_file_name or None,
        },
    ).execute()
    return response.data


def reverse_consumable_batch(supabase, batch_id, created_by):
    response = supabase.rpc(
        "reverse_consumable_movement_batch",
        {
            "p_batch_id": str(batch_id),
            "p_created_by": created_by,
        },
    ).execute()
    return response.data
