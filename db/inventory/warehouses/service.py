import pandas as pd

from utils.sku_sorting import sort_sku_rows


WAREHOUSE_CODES = ("25", "60", "70")
TRANSFER_STATUS_LABELS = {
    "pending": "待配货",
    "in_transit": "运输中",
    "completed": "已收到",
    "cancelled": "已取消",
    "reversed": "已撤销",
}


def build_warehouse_distribution(
    inventory_items, balances, transfer_orders=None, transfer_lines=None,
):
    columns = [
        "库存ID", "部门", "品类", "材质", "品牌", "颜色", "尺码",
        "25仓", "60仓", "70仓", "在途/待核对", "未分配差额", "总库存",
        "25库位", "60库位", "70库位",
    ]
    items = pd.DataFrame(inventory_items).copy()
    if items.empty:
        return pd.DataFrame(columns=columns)
    items = items.rename(columns={
        "id": "库存ID", "department": "部门", "category": "品类",
        "material": "材质", "brand": "品牌", "color": "颜色",
        "size": "尺码", "quantity": "总库存",
    })
    balance = pd.DataFrame(balances).copy()
    if balance.empty:
        quantities = pd.DataFrame({"库存ID": items["库存ID"]})
        locations = quantities.copy()
    else:
        quantities = balance.pivot_table(
            index="inventory_item_id", columns="warehouse_code",
            values="quantity", aggfunc="sum", fill_value=0,
        ).reset_index().rename(columns={"inventory_item_id": "库存ID"})
        location_source = balance.copy()
        location_source["location_note"] = (
            location_source["location_note"].fillna("").astype(str).str.strip()
        )
        locations = location_source.pivot_table(
            index="inventory_item_id", columns="warehouse_code",
            values="location_note", aggfunc=_join_notes, fill_value="",
        ).reset_index().rename(columns={"inventory_item_id": "库存ID"})
    for code in WAREHOUSE_CODES:
        if code not in quantities:
            quantities[code] = 0
        if code not in locations:
            locations[code] = ""
    quantities = quantities.rename(columns={
        code: f"{code}仓" for code in WAREHOUSE_CODES
    })
    locations = locations.rename(columns={
        code: f"{code}库位" for code in WAREHOUSE_CODES
    })
    result = items.merge(quantities, on="库存ID", how="left").merge(
        locations, on="库存ID", how="left"
    )
    in_transit = _build_in_transit(
        transfer_orders, transfer_lines
    )
    result = result.merge(in_transit, on="库存ID", how="left")
    numeric = ["总库存", *[f"{code}仓" for code in WAREHOUSE_CODES]]
    for column in numeric:
        result[column] = pd.to_numeric(
            result.get(column, 0), errors="coerce"
        ).fillna(0).astype(int)
    result["在途/待核对"] = pd.to_numeric(
        result.get("在途/待核对", 0), errors="coerce"
    ).fillna(0).astype(int)
    result["未分配差额"] = (
        result["总库存"]
        - result[[f"{code}仓" for code in WAREHOUSE_CODES]].sum(axis=1)
        - result["在途/待核对"]
    )
    for code in WAREHOUSE_CODES:
        result[f"{code}库位"] = result[f"{code}库位"].fillna("")
    result = sort_sku_rows(
        result,
        material="材质", color="颜色", size="尺码",
        leading=["部门", "品类", "品牌"],
    )
    return result[columns].reset_index(drop=True)


def build_transfer_line_editor(lines, mode="dispatch"):
    source = pd.DataFrame(lines).copy()
    if source.empty:
        return pd.DataFrame()
    result = source.rename(columns={
        "id": "明细ID", "inventory_item_id": "库存ID",
        "department": "部门", "category": "品类",
        "material": "材质", "brand": "品牌", "color": "颜色",
        "size": "尺码", "quantity_sent": "已发出",
        "quantity_received": "已收到", "source_location": "来源库位",
        "target_location": "目标库位", "note": "备注",
    })
    if mode == "receive":
        result["本次收到"] = pd.to_numeric(
            result["已发出"], errors="coerce"
        ).fillna(0).astype(int)
        columns = [
            "明细ID", "库存ID", "部门", "品类", "材质", "品牌",
            "颜色", "尺码", "已发出", "本次收到", "目标库位", "备注",
        ]
    else:
        result["实际发出"] = pd.to_numeric(
            result.get("已发出", 0), errors="coerce"
        ).fillna(0).astype(int)
        columns = [
            "明细ID", "库存ID", "部门", "品类", "材质", "品牌",
            "颜色", "尺码", "实际发出", "来源库位", "目标库位", "备注",
        ]
    return sort_sku_rows(
        result[columns], material="材质", color="颜色", size="尺码",
        leading=["部门", "品类", "品牌"],
    ).reset_index(drop=True)


def normalize_transfer_execution_lines(editor, mode="dispatch", direct=False):
    rows = []
    quantity_column = "本次收到" if mode == "receive" else "实际发出"
    for row in pd.DataFrame(editor).to_dict("records"):
        quantity = int(pd.to_numeric(
            pd.Series([row.get(quantity_column, 0)]), errors="coerce"
        ).fillna(0).iloc[0])
        if quantity < 0:
            raise ValueError("调拨数量不能小于 0")
        payload = {
            "quantity": quantity,
            "source_location": str(row.get("来源库位") or "").strip(),
            "target_location": str(row.get("目标库位") or "").strip(),
            "note": str(row.get("备注") or "").strip(),
        }
        if direct:
            payload["inventory_item_id"] = str(row["库存ID"])
        else:
            payload["line_id"] = str(row["明细ID"])
        rows.append(payload)
    return rows


def _build_in_transit(orders, lines):
    order_frame = pd.DataFrame(orders).copy()
    line_frame = pd.DataFrame(lines).copy()
    empty = pd.DataFrame(columns=["库存ID", "在途/待核对"])
    if order_frame.empty or line_frame.empty:
        return empty
    active_ids = set(order_frame.loc[
        order_frame["status"].isin(["in_transit", "completed"]), "id"
    ].astype(str))
    if not active_ids:
        return empty
    active = line_frame[
        line_frame["transfer_order_id"].astype(str).isin(active_ids)
    ].copy()
    if active.empty:
        return empty
    sent = pd.to_numeric(active["quantity_sent"], errors="coerce").fillna(0)
    received = pd.to_numeric(
        active["quantity_received"], errors="coerce"
    ).fillna(0)
    active["在途/待核对"] = (sent - received).clip(lower=0).astype(int)
    return (
        active.groupby("inventory_item_id", as_index=False)["在途/待核对"]
        .sum().rename(columns={"inventory_item_id": "库存ID"})
    )


def _join_notes(values):
    return "；".join(dict.fromkeys(
        str(value).strip() for value in values if str(value).strip()
    ))
