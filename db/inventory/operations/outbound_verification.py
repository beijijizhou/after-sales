"""Validate outbound inventory availability and persisted batch rows."""

from collections import Counter

import pandas as pd


def find_outbound_inventory_issues(expected_df, inventory_df):
    keys = ["品牌", "材质", "款式", "颜色", "尺码"]
    expected_df = pd.DataFrame(expected_df).copy()
    inventory_df = pd.DataFrame(inventory_df).copy()
    if "款式" not in expected_df:
        expected_df["款式"] = ""
    if "style" not in inventory_df:
        inventory_df["style"] = ""
    expected = expected_df.groupby(keys, as_index=False)["数量"].sum()
    inventory = inventory_df.rename(columns={
        "brand": "品牌", "material": "材质", "style": "款式", "color": "颜色",
        "size": "尺码", "quantity": "当前库存",
    })
    available = [*keys, "当前库存"]
    inventory = (
        inventory[available] if not inventory.empty
        else pd.DataFrame(columns=available)
    )
    result = expected.merge(inventory, on=keys, how="left", indicator=True)
    result["当前库存"] = pd.to_numeric(
        result["当前库存"], errors="coerce"
    ).fillna(0).astype(int)
    result["缺口"] = (result["数量"] - result["当前库存"]).clip(lower=0)
    result["问题"] = result["_merge"].map({
        "left_only": "SKU 不存在", "both": "库存不足", "right_only": "",
    }).astype(str)
    return result[result["缺口"] > 0][
        [*keys, "数量", "当前库存", "缺口", "问题"]
    ].reset_index(drop=True)


def find_outbound_warehouse_shortages(
    expected_df, inventory_df, balances_df, warehouse_code="25",
):
    """Return SKUs whose issuing-warehouse balance cannot cover the outbound.

    Daily outbound always deducts from one warehouse. A SKU can have enough
    company-wide stock while the issuing warehouse is short because the rest
    sits in a reserve warehouse; that needs a transfer, not a stock adjustment.
    """
    keys = ["品牌", "材质", "款式", "颜色", "尺码"]
    columns = [
        "inventory_item_id", *keys, "数量", "当前库存", "出库仓库存",
        "其他仓库存", "出库仓缺口",
    ]
    expected_df = pd.DataFrame(expected_df).copy()
    inventory_df = pd.DataFrame(inventory_df).copy()
    if expected_df.empty or inventory_df.empty or "id" not in inventory_df:
        return pd.DataFrame(columns=columns)
    if "款式" not in expected_df:
        expected_df["款式"] = ""
    if "style" not in inventory_df:
        inventory_df["style"] = ""
    expected_df["款式"] = expected_df["款式"].fillna("")
    inventory_df["style"] = inventory_df["style"].fillna("")
    expected = expected_df.groupby(keys, as_index=False)["数量"].sum()
    inventory = inventory_df.rename(columns={
        "brand": "品牌", "material": "材质", "style": "款式", "color": "颜色",
        "size": "尺码", "quantity": "当前库存",
    })[["id", *keys, "当前库存"]]
    result = expected.merge(inventory, on=keys, how="inner")
    balances = pd.DataFrame(balances_df).copy()
    if balances.empty:
        balances = pd.DataFrame(
            columns=["inventory_item_id", "warehouse_code", "quantity"]
        )
    balances["quantity"] = pd.to_numeric(
        balances["quantity"], errors="coerce"
    ).fillna(0).astype(int)
    issuing = balances["warehouse_code"].astype(str) == str(warehouse_code)
    result["出库仓库存"] = result["id"].map(
        balances[issuing].groupby("inventory_item_id")["quantity"].sum()
    ).fillna(0).astype(int)
    result["其他仓库存"] = result["id"].map(
        balances[~issuing].groupby("inventory_item_id")["quantity"].sum()
    ).fillna(0).astype(int)
    result["当前库存"] = pd.to_numeric(
        result["当前库存"], errors="coerce"
    ).fillna(0).astype(int)
    result["inventory_item_id"] = result["id"]
    deductible = result[["数量", "当前库存"]].min(axis=1)
    result["出库仓缺口"] = (deductible - result["出库仓库存"]).clip(lower=0)
    return result[result["出库仓缺口"] > 0][columns].reset_index(drop=True)


def verify_outbound_batch(supabase, batch_id, expected_df=None):
    rows = _load_outbound_batch(supabase, batch_id)
    saved_total = sum(abs(int(row["quantity_change"])) for row in rows)
    rows_match = (
        True if expected_df is None
        else _movement_signatures(rows) == _expected_signatures(expected_df)
    )
    return len(rows), saved_total, rows_match


def audit_outbound_batch(supabase, batch_id, expected_df):
    rows = _load_outbound_batch(supabase, batch_id)
    expected_total = int(expected_df["数量"].sum())
    saved_total = sum(abs(int(row["quantity_change"])) for row in rows)
    rows_match = _movement_signatures(rows) == _expected_signatures(expected_df)
    result = {
        "batch_id": str(batch_id), "expected_row_count": len(expected_df),
        "saved_row_count": len(rows), "expected_total": expected_total,
        "saved_total": saved_total, "difference": saved_total - expected_total,
        "rows_match": rows_match,
    }
    result["passed"] = (
        result["expected_row_count"] == result["saved_row_count"]
        and result["difference"] == 0 and rows_match
    )
    return result, _build_outbound_mismatches(rows, expected_df)


def _load_outbound_batch(supabase, batch_id):
    return (
        supabase.table("inventory_movements")
        .select("movement_date,brand,material,style,color,size,quantity_change")
        .eq("batch_id", str(batch_id)).execute().data or []
    )


def _build_outbound_mismatches(rows, expected_df):
    keys = ["日期", "品牌", "材质", "款式", "颜色", "尺码"]
    expected = expected_df.copy()
    if "款式" not in expected:
        expected["款式"] = ""
    expected["日期"] = pd.to_datetime(
        expected["日期"], errors="coerce"
    ).dt.date.astype(str)
    expected = expected.groupby(keys, as_index=False)["数量"].sum().rename(
        columns={"数量": "提交件数"}
    )
    saved = pd.DataFrame(rows)
    if saved.empty:
        saved = pd.DataFrame(columns=[
            "movement_date", "brand", "material", "style", "color", "size",
            "quantity_change",
        ])
    saved = saved.rename(columns={
        "movement_date": "日期", "brand": "品牌", "material": "材质",
        "style": "款式", "color": "颜色", "size": "尺码",
        "quantity_change": "数据库变化",
    })
    if "款式" not in saved:
        saved["款式"] = ""
    saved["日期"] = saved["日期"].astype(str)
    saved["数据库件数"] = pd.to_numeric(
        saved["数据库变化"], errors="coerce"
    ).fillna(0).abs().astype(int)
    saved = saved.groupby(keys, as_index=False)["数据库件数"].sum()
    comparison = expected.merge(saved, on=keys, how="outer").fillna(0)
    comparison["提交件数"] = comparison["提交件数"].astype(int)
    comparison["数据库件数"] = comparison["数据库件数"].astype(int)
    comparison["差额"] = comparison["数据库件数"] - comparison["提交件数"]
    return comparison[comparison["差额"] != 0].reset_index(drop=True)


def _movement_signatures(rows):
    return Counter(
        (
            str(row.get("movement_date")), str(row.get("brand") or "").strip(),
            str(row.get("material") or "").strip(),
            str(row.get("style") or "").strip(),
            str(row.get("color") or "").strip(),
            str(row.get("size") or "").strip().upper(),
            int(row.get("quantity_change") or 0),
        )
        for row in rows
    )


def _expected_signatures(expected_df):
    signatures = []
    for row in expected_df.to_dict("records"):
        movement_date = pd.to_datetime(row.get("日期"), errors="coerce")
        quantity = int(row.get("数量") or 0)
        if row.get("操作") == "扣减":
            quantity = -quantity
        signatures.append((
            movement_date.date().isoformat(),
            str(row.get("品牌") or "").strip(),
            str(row.get("材质") or "").strip(),
            str(row.get("款式") or "").strip(),
            str(row.get("颜色") or "").strip(),
            str(row.get("尺码") or "").strip().upper(), quantity,
        ))
    return Counter(signatures)
