from datetime import datetime
from zoneinfo import ZoneInfo

from db.supabase_client import supabase

NY_TIMEZONE = ZoneInfo("America/New_York")


def chunk_list(values, size):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def normalize_barcode(value):
    return str(value).strip().upper()


def save_after_sales(barcode: str, scanned_by: str):
    return (
        supabase
        .table("after_sales")
        .upsert({
            "barcode": normalize_barcode(barcode),
            "scanned_by": scanned_by,
        })
        .execute()
    )


def load_after_sales_by_barcodes(barcodes):
    rows = []
    unique_barcodes = list(dict.fromkeys(
        normalize_barcode(barcode)
        for barcode in barcodes
        if normalize_barcode(barcode)
    ))

    for barcode_group in chunk_list(unique_barcodes, 100):
        try:
            response = (
                supabase
                .table("after_sales")
                .select("barcode,reason,amount,product_type,quantity,scanned_at,entered_at")
                .in_("barcode", barcode_group)
                .execute()
            )
        except Exception:
            response = (
                supabase
                .table("after_sales")
                .select("barcode,reason")
                .in_("barcode", barcode_group)
                .execute()
            )
            for row in response.data:
                row["amount"] = 0
                row["product_type"] = "短袖"
                row["quantity"] = 1
                row["scanned_at"] = None
                row["entered_at"] = None
        rows.extend(response.data)

    return {
        normalize_barcode(row["barcode"]): row
        for row in rows
    }


def enrich_after_sales_status(df):
    if df.empty or "barcode" not in df.columns:
        return df

    enriched_df = df.copy()
    enriched_df["barcode"] = enriched_df["barcode"].apply(normalize_barcode)
    after_sales_by_barcode = load_after_sales_by_barcodes(enriched_df["barcode"])
    enriched_df["是否已售后"] = enriched_df["barcode"].apply(
        lambda barcode: "是" if barcode in after_sales_by_barcode else "否"
    )
    enriched_df["售后原因"] = enriched_df["barcode"].apply(
        lambda barcode: after_sales_by_barcode.get(barcode, {}).get("reason", "")
    )
    enriched_df["总金额"] = enriched_df["barcode"].apply(
        lambda barcode: after_sales_by_barcode.get(barcode, {}).get("amount", 0)
    )
    enriched_df["售后类型"] = enriched_df["barcode"].apply(
        lambda barcode: after_sales_by_barcode.get(barcode, {}).get("product_type", "短袖")
    )
    enriched_df["件数"] = enriched_df["barcode"].apply(
        lambda barcode: after_sales_by_barcode.get(barcode, {}).get("quantity", 1)
    )
    enriched_df["scanned_at"] = enriched_df.apply(
        lambda row: after_sales_by_barcode.get(
            row["barcode"], {}
        ).get("scanned_at", row.get("scanned_at")),
        axis=1,
    )
    return enriched_df


def save_after_sales_batch(df):
    records = [
        {
            "barcode": normalize_barcode(row["barcode"]),
            "scanned_by": row["scanned_by"],
            "reason": row.get("售后原因", ""),
            "amount": clean_amount(row.get("总金额", 0)),
            "product_type": clean_product_type(row.get("售后类型", "短袖")),
            "quantity": clean_quantity(row.get("件数", 1)),
            "scanned_at": row.get("scanned_at"),
            "entered_at": datetime.now(NY_TIMEZONE).isoformat(),
        }
        for _, row in df.iterrows()
    ]

    return (
        supabase
        .table("after_sales")
        .upsert(records)
        .execute()
    )


def load_after_sales_people_summary():
    try:
        response = (
            supabase
            .table("after_sales")
            .select("scanned_by,amount,quantity,scanned_at,entered_at")
            .execute()
        )
    except Exception:
        response = (
            supabase
            .table("after_sales")
            .select("scanned_by,amount,quantity")
            .execute()
        )
        for row in response.data:
            row["scanned_at"] = None
            row["entered_at"] = None
    return response.data


def load_after_sales_detail_by_person(person):
    try:
        response = (
            supabase
            .table("after_sales")
            .select("barcode,scanned_by,product_type,quantity,amount,reason,scanned_at,entered_at")
            .eq("scanned_by", person)
            .order("barcode")
            .execute()
        )
    except Exception:
        response = (
            supabase
            .table("after_sales")
            .select("barcode,scanned_by,reason")
            .eq("scanned_by", person)
            .order("barcode")
            .execute()
        )
        for row in response.data:
            row["product_type"] = "短袖"
            row["quantity"] = 1
            row["amount"] = 0
            row["scanned_at"] = None
            row["entered_at"] = None
    return response.data


def clean_amount(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def clean_quantity(value):
    try:
        return max(int(value or 1), 1)
    except (TypeError, ValueError):
        return 1


def clean_product_type(value):
    return value if value in {"短袖", "卫衣"} else "短袖"
