from db.logistics.repository import save_label_review


def save_reviewed_ocr_results(supabase, reviewed_rows, shipments, reviewer):
    if shipments is None or shipments.empty:
        return 0
    saved_count = 0
    shipment_rows = shipments.to_dict("records")
    for item in reviewed_rows:
        row = item.get("row", item)
        matches = _matching_shipments(shipment_rows, row)
        for shipment in matches:
            status = str(row.get("ocr_status") or "").strip()
            error = "" if status == "已识别" else status
            save_label_review(
                supabase,
                shipment["id"],
                dict(row.get("_ocr_fields") or {}),
                reviewer,
                label_url=(row.get("label_url") or row.get("backup_label_url")),
                ocr_status=status,
                ocr_error=error,
                engine_version="rapidocr-v4",
            )
            saved_count += 1
    return saved_count


def _matching_shipments(shipments, row):
    tracking = str(row.get("tracking_number") or "").strip()
    order_id = str(row.get("external_order_id") or "").strip()
    matches = [
        shipment for shipment in shipments
        if str(shipment.get("tracking_number") or "").strip() == tracking
    ]
    if order_id:
        matches = [
            shipment for shipment in matches
            if str(shipment.get("external_order_id") or "").strip() == order_id
        ]
    return matches
