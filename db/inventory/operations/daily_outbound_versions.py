import pandas as pd

from db.inventory.operations.adjustments import reverse_inventory_batch


NO_OUTBOUND_ACK_PREFIX = "completion_ack｜当日无出库"


def acknowledge_no_daily_outbound(
    supabase, department, category, movement_date, created_by, note="",
):
    """Record an audited zero-change completion for one business date."""
    operator = str(created_by or "").strip() or "system"
    batches = (
        supabase.table("inventory_daily_outbound_batches")
        .select("id,current_revision,status")
        .eq("department", department)
        .eq("category", category)
        .eq("movement_date", movement_date.isoformat())
        .limit(1)
        .execute()
        .data
        or []
    )
    if batches:
        batch = batches[0]
        current_revision = int(batch.get("current_revision") or 0)
        if current_revision:
            revisions = (
                supabase.table("inventory_daily_outbound_revisions")
                .select("id,requested_total,note")
                .eq("daily_outbound_batch_id", batch["id"])
                .eq("revision_number", current_revision)
                .limit(1)
                .execute()
                .data
                or []
            )
            current = revisions[0] if revisions else {}
            current_note = str(current.get("note") or "")
            if (
                batch.get("status") == "active"
                and int(current.get("requested_total") or 0) == 0
                and current_note.startswith(NO_OUTBOUND_ACK_PREFIX)
            ):
                return {
                    "daily_outbound_batch_id": batch["id"],
                    "revision_id": current.get("id"),
                    "revision_number": current_revision,
                    "status": "acknowledged",
                }
            if (
                batch.get("status") == "active"
                and int(current.get("requested_total") or 0) > 0
            ):
                raise ValueError("该日期已有正式出库批次，不能确认为无出库")
    else:
        inserted = (
            supabase.table("inventory_daily_outbound_batches")
            .insert({
                "department": department,
                "category": category,
                "movement_date": movement_date.isoformat(),
                "created_by": operator,
                "updated_by": operator,
            })
            .execute()
            .data
            or []
        )
        if not inserted:
            raise ValueError("无法创建无出库核对批次")
        batch = inserted[0]
        current_revision = 0

    next_revision = current_revision + 1
    full_note = NO_OUTBOUND_ACK_PREFIX
    if str(note or "").strip():
        full_note += f"｜{str(note).strip()}"
    revision = (
        supabase.table("inventory_daily_outbound_revisions")
        .insert({
            "daily_outbound_batch_id": batch["id"],
            "revision_number": next_revision,
            "action": "create" if next_revision == 1 else "edit",
            "inventory_batch_id": None,
            "reversal_inventory_batch_id": None,
            "requested_total": 0,
            "applied_total": 0,
            "shortage_total": 0,
            "note": full_note,
            "created_by": operator,
        })
        .execute()
        .data
        or []
    )
    (
        supabase.table("inventory_daily_outbound_batches")
        .update({
            "current_revision": next_revision,
            "status": "active",
            "updated_by": operator,
        })
        .eq("id", batch["id"])
        .execute()
    )
    return {
        "daily_outbound_batch_id": batch["id"],
        "revision_id": revision[0]["id"] if revision else None,
        "revision_number": next_revision,
        "status": "acknowledged",
    }


def save_daily_outbound_revision(
    supabase,
    department,
    category,
    movement_date,
    rows,
    created_by,
    daily_outbound_batch_id=None,
    note=None,
):
    prepared = []
    for row in pd.DataFrame(rows).to_dict("records"):
        numeric = pd.to_numeric(row.get("数量"), errors="coerce")
        quantity = 0 if pd.isna(numeric) else int(numeric)
        if quantity <= 0:
            continue
        prepared.append({
            "brand": str(row.get("品牌") or "").strip(),
            "material": str(row.get("材质") or "").strip(),
            "color": str(row.get("颜色") or "").strip(),
            "size": str(row.get("尺码") or "").strip().upper(),
            "requested_quantity": quantity,
        })
    if not prepared:
        raise ValueError("每日出库不能为空")
    response = supabase.rpc(
        "save_inventory_daily_outbound_revision",
        {
            "p_department": department,
            "p_category": category,
            "p_movement_date": movement_date.isoformat(),
            "p_rows": prepared,
            "p_created_by": created_by,
            "p_daily_outbound_batch_id": daily_outbound_batch_id,
            "p_note": note,
        },
    ).execute()
    return response.data or {}


def void_daily_outbound_revision(
    supabase, daily_outbound_batch_id, department, category, created_by,
    note="撤销每日出库",
):
    """Void the current logical revision and restore its inventory impact."""
    batch = (
        supabase.table("inventory_daily_outbound_batches")
        .select("id,current_revision,status")
        .eq("id", str(daily_outbound_batch_id)).single().execute().data
    )
    if not batch:
        raise ValueError("没有找到每日出库业务批次")
    if batch.get("status") == "voided":
        return {"daily_outbound_batch_id": batch["id"], "status": "voided"}
    current = (
        supabase.table("inventory_daily_outbound_revisions")
        .select("id,inventory_batch_id")
        .eq("daily_outbound_batch_id", batch["id"])
        .eq("revision_number", int(batch["current_revision"]))
        .single().execute().data
    )
    if not current:
        raise ValueError("没有找到每日出库当前版本")
    inventory_batch_id = current.get("inventory_batch_id")
    reversal_batch_id = None
    if inventory_batch_id:
        reversal_batch_id = reverse_inventory_batch(
            supabase, inventory_batch_id, department, category, created_by
        )
    next_revision = int(batch["current_revision"]) + 1
    try:
        revision = (
            supabase.table("inventory_daily_outbound_revisions").insert({
                "daily_outbound_batch_id": batch["id"],
                "revision_number": next_revision,
                "action": "void",
                "inventory_batch_id": None,
                "reversal_inventory_batch_id": reversal_batch_id,
                "requested_total": 0,
                "applied_total": 0,
                "shortage_total": 0,
                "note": note,
                "created_by": created_by,
            }).execute().data
        )
        (
            supabase.table("inventory_daily_outbound_batches").update({
                "current_revision": next_revision,
                "status": "voided",
                "updated_by": created_by,
            }).eq("id", batch["id"]).execute()
        )
    except Exception:
        if reversal_batch_id:
            reverse_inventory_batch(
                supabase, reversal_batch_id, department, category, created_by
            )
        raise
    return {
        "daily_outbound_batch_id": batch["id"],
        "revision_id": revision[0]["id"] if revision else None,
        "revision_number": next_revision,
        "reversal_inventory_batch_id": reversal_batch_id,
        "status": "voided",
    }


def load_daily_outbound_revisions(
    supabase, department, category, start_date=None, end_date=None,
):
    query = (
        supabase.table("inventory_daily_outbound_batches")
        .select(
            "id,department,category,movement_date,current_revision,status,"
            "created_by,created_at,updated_by,updated_at,"
            "inventory_daily_outbound_revisions("
            "id,revision_number,action,inventory_batch_id,"
            "reversal_inventory_batch_id,requested_total,applied_total,"
            "shortage_total,note,created_by,created_at,"
            "inventory_daily_outbound_lines(brand,material,color,size,"
            "requested_quantity,applied_quantity,shortage_quantity))"
        )
        .eq("department", department)
        .eq("category", category)
    )
    if start_date:
        query = query.gte("movement_date", start_date.isoformat())
    if end_date:
        query = query.lte("movement_date", end_date.isoformat())
    return query.order("movement_date", desc=True).execute().data or []


def load_daily_outbound_revision_by_inventory_batch(
    supabase, inventory_batch_id,
):
    rows = (
        supabase.table("inventory_daily_outbound_revisions")
        .select(
            "id,daily_outbound_batch_id,revision_number,"
            "inventory_daily_outbound_lines(brand,material,color,size,"
            "requested_quantity,applied_quantity,shortage_quantity),"
            "inventory_daily_outbound_batches("
            "department,category,movement_date,current_revision,status)"
        )
        .eq("inventory_batch_id", str(inventory_batch_id))
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def build_daily_outbound_edit_rows(revision):
    if not revision:
        return pd.DataFrame()
    batch = revision.get("inventory_daily_outbound_batches") or {}
    movement_date = pd.to_datetime(
        batch.get("movement_date"), errors="coerce"
    ).date()
    return pd.DataFrame([{
        "日期": movement_date,
        "操作": "扣减",
        "品牌": line.get("brand") or "",
        "材质": line.get("material") or "",
        "颜色": line.get("color") or "",
        "尺码": line.get("size") or "",
        "数量": int(line.get("requested_quantity") or 0),
        "成本": pd.NA,
        "备注": "仓库每日出货",
    } for line in revision.get("inventory_daily_outbound_lines", [])])
