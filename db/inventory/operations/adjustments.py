from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd

from db.inventory.core.constants import SIZE_COLUMNS
from db.inventory.core.snapshots import create_inventory_snapshot


def build_adjustment_template():
    return pd.DataFrame(columns=["日期", "操作", "品牌", "材质", "颜色", "尺码", "数量", "备注"])


def build_wide_adjustment_template():
    return pd.DataFrame(columns=["日期", "品牌", "材质", "颜色", *SIZE_COLUMNS, "备注"])


def normalize_wide_adjustment_rows(df):
    required_columns = {"日期", "操作", "材质", "颜色", *SIZE_COLUMNS}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"缺少列：{', '.join(sorted(missing_columns))}")

    df = df.copy()
    df["日期"] = pd.to_datetime(df["日期"], errors="coerce").dt.date
    df["操作"] = df["操作"].astype(str).str.strip()
    if "品牌" not in df.columns:
        df["品牌"] = ""
    df["品牌"] = df["品牌"].fillna("").astype(str).str.strip()
    df["材质"] = df["材质"].fillna("180g").astype(str).str.strip()
    df["颜色"] = df["颜色"].astype(str).str.strip()
    if "备注" not in df.columns:
        df["备注"] = ""
    df["备注"] = df["备注"].fillna("").astype(str).str.strip()
    if "成本" not in df.columns:
        df["成本"] = pd.NA
    df["成本"] = pd.to_numeric(df["成本"], errors="coerce")
    row_columns = ["入库行"] if "入库行" in df.columns else []
    for size in SIZE_COLUMNS:
        df[size] = pd.to_numeric(df[size], errors="coerce").fillna(0).astype(int)
    if "设置此行" in df.columns:
        selected_for_setting = df["设置此行"].fillna(False).astype(bool)
    else:
        selected_for_setting = pd.Series(False, index=df.index)
    df["_设置行"] = selected_for_setting | (df[SIZE_COLUMNS].sum(axis=1) > 0)

    df = df.dropna(subset=["日期"])
    df["操作"] = df["操作"].replace({"减少": "扣减"})
    df = df[(df["材质"] != "") & (df["颜色"] != "") & (df["操作"].isin(["增加", "扣减", "设置"]))]
    adjustment_df = df.melt(
        id_vars=[
            "日期", "操作", "品牌", "材质", "颜色", "成本", "备注",
            *row_columns, "_设置行",
        ],
        value_vars=SIZE_COLUMNS,
        var_name="尺码",
        value_name="数量",
    )
    setting_rows = adjustment_df["操作"].eq("设置") & adjustment_df["_设置行"]
    adjustment_df = adjustment_df[setting_rows | (adjustment_df["数量"] > 0)]
    columns = [
        "日期", "操作", "品牌", "材质", "颜色", "尺码", "数量",
        "成本", "备注", *row_columns,
    ]
    return adjustment_df[columns].reset_index(drop=True)


def normalize_adjustment_rows(df):
    if set(SIZE_COLUMNS).issubset(df.columns):
        return normalize_wide_adjustment_rows(df)

    required_columns = {"日期", "操作", "材质", "颜色", "尺码", "数量"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"缺少列：{', '.join(sorted(missing_columns))}")

    df = df.copy()
    df["日期"] = pd.to_datetime(df["日期"], errors="coerce").dt.date
    df["操作"] = df["操作"].astype(str).str.strip()
    if "品牌" not in df.columns:
        df["品牌"] = ""
    df["品牌"] = df["品牌"].fillna("").astype(str).str.strip()
    df["材质"] = df["材质"].fillna("180g").astype(str).str.strip()
    df["颜色"] = df["颜色"].astype(str).str.strip()
    df["尺码"] = df["尺码"].astype(str).str.strip().str.upper()
    df["数量"] = pd.to_numeric(df["数量"], errors="coerce").fillna(0).astype(int)
    if "备注" not in df.columns:
        df["备注"] = ""
    df["备注"] = df["备注"].fillna("").astype(str).str.strip()
    if "成本" not in df.columns:
        df["成本"] = pd.NA
    df["成本"] = pd.to_numeric(df["成本"], errors="coerce")

    df = df.dropna(subset=["日期"])
    df = df[df["数量"] > 0]
    df["操作"] = df["操作"].replace({"减少": "扣减"})
    df = df[df["操作"].isin(["增加", "扣减", "设置"])]
    df = df[df["材质"] != ""]
    df = df[df["尺码"].isin(SIZE_COLUMNS)]
    columns = ["日期", "操作", "品牌", "材质", "颜色", "尺码", "数量", "成本", "备注"]
    return df[columns].reset_index(drop=True)


def parse_adjustment_file(uploaded_file):
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    return normalize_adjustment_rows(df)


def apply_adjustment_rows(
    supabase, department, category, df, created_by="system",
    source_type="bulk", batch_id=None,
):
    batch_id = str(batch_id or uuid4())
    records = []
    for row in df.to_dict("records"):
        quantity_change = int(row["数量"]) if row["操作"] == "增加" else -int(row["数量"])
        record = {
            "brand": row["品牌"],
            "material": row["材质"],
            "color": row["颜色"],
            "size": row["尺码"],
            "quantity_change": quantity_change,
            "reason": row["备注"],
            "movement_date": row["日期"].isoformat(),
            "source_type": source_type,
        }
        if not pd.isna(row.get("成本")):
            record["unit_cost"] = float(row["成本"])
        records.append(record)

    parameters = {
        "p_department": department,
        "p_category": category,
        "p_rows": records,
        "p_batch_id": batch_id,
        "p_created_by": created_by,
        "p_source_type": source_type,
    }
    try:
        supabase.rpc(
            "apply_inventory_adjustment_batch", parameters
        ).execute()
    except Exception as error:
        if "PGRST202" not in str(error):
            raise
        legacy_parameters = dict(parameters)
        legacy_parameters.pop("p_source_type")
        legacy_parameters["p_rows"] = [
            {
                key: value for key, value in record.items()
                if key != "source_type"
            }
            for record in records
        ]
        supabase.rpc(
            "apply_inventory_adjustment_batch", legacy_parameters
        ).execute()
    for movement_date in sorted(df["日期"].dropna().unique()):
        create_inventory_snapshot(supabase, department, category, movement_date)
    return batch_id


def apply_stocktake_rows(
    supabase, department, category, df, created_by="system", batch_id=None,
):
    """Set selected SKU balances to audited physical-count targets."""
    batch_id = str(batch_id or uuid4())
    existing_rows = (
        supabase.table("inventory_items")
        .select("brand,material,color,size")
        .eq("department", department)
        .eq("category", category)
        .execute()
        .data
        or []
    )
    existing = {
        (
            str(row.get("brand") or "").strip(),
            str(row.get("material") or "").strip(),
            str(row.get("color") or "").strip(),
            str(row.get("size") or "").strip().upper(),
        )
        for row in existing_rows
    }
    records = []
    for row in df.to_dict("records"):
        identity = (
            str(row["品牌"] or "").strip(),
            str(row["材质"] or "").strip(),
            str(row["颜色"] or "").strip(),
            str(row["尺码"] or "").strip().upper(),
        )
        target_quantity = int(row["数量"])
        if target_quantity == 0 and identity not in existing:
            continue
        note = str(row.get("备注") or "").strip()
        reason = (
            note if "库存盘点设置" in note
            else f"库存盘点设置｜{note}" if note
            else "库存盘点设置"
        )
        records.append({
            "brand": identity[0],
            "material": identity[1],
            "color": identity[2],
            "size": identity[3],
            "target_quantity": target_quantity,
            "reason": reason,
            "movement_date": row["日期"].isoformat(),
        })
    if not records:
        raise ValueError("没有需要设置的现有 SKU")
    response = supabase.rpc("apply_inventory_stocktake_batch", {
        "p_department": department,
        "p_category": category,
        "p_rows": records,
        "p_batch_id": batch_id,
        "p_created_by": created_by,
    }).execute()
    for movement_date in sorted(df["日期"].dropna().unique()):
        create_inventory_snapshot(supabase, department, category, movement_date)
    return response.data or batch_id


def reverse_inventory_batch(
    supabase, batch_id, department, category, created_by="system"
):
    response = supabase.rpc(
        "reverse_inventory_movement_batch",
        {"p_batch_id": batch_id, "p_created_by": created_by},
    ).execute()
    today = datetime.now(ZoneInfo("America/New_York")).date()
    create_inventory_snapshot(supabase, department, category, today)
    return response.data
