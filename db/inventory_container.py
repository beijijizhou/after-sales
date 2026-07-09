from datetime import date

import pandas as pd

from db.inventory import DEFAULT_CATEGORY, DEFAULT_DEPARTMENT, SIZE_COLUMNS


CONTAINER_STATUSES = ["未到货", "已到货", "延迟", "取消"]


def load_inventory_containers(supabase, start_date=None, end_date=None, department=None, category=None):
    query = (
        supabase
        .table("inventory_container_imports")
        .select("expected_arrival_date,container_no,department,category,brand,material,color,size,quantity,unit_cost,status,note,created_at")
    )
    if start_date is not None:
        query = query.gte("expected_arrival_date", start_date.isoformat())
    if end_date is not None:
        query = query.lte("expected_arrival_date", end_date.isoformat())
    if department:
        query = query.eq("department", department)
    if category:
        query = query.eq("category", category)

    response = (
        query
        .order("expected_arrival_date", desc=False)
        .order("created_at", desc=False)
        .execute()
    )
    return pd.DataFrame(response.data)


def build_container_template(today=None):
    today = today or date.today()
    return pd.DataFrame([{
        "预计到货日期": today,
        "货柜号": "",
        "部门": DEFAULT_DEPARTMENT,
        "品类": DEFAULT_CATEGORY,
        "品牌": "",
        "材质": "180g",
        "颜色": "",
        **{size: 0 for size in SIZE_COLUMNS},
        "状态": "未到货",
        "备注": "",
    }])


def normalize_container_rows(df):
    required_columns = {"预计到货日期", "部门", "材质", "颜色", *SIZE_COLUMNS}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"缺少列：{', '.join(sorted(missing_columns))}")

    df = df.copy()
    if "货柜号" not in df.columns:
        df["货柜号"] = ""
    if "品类" not in df.columns:
        df["品类"] = ""
    if "品牌" not in df.columns:
        df["品牌"] = ""
    if "成本" not in df.columns:
        df["成本"] = 0
    if "状态" not in df.columns:
        df["状态"] = "未到货"
    if "备注" not in df.columns:
        df["备注"] = ""

    df["预计到货日期"] = pd.to_datetime(df["预计到货日期"], errors="coerce").dt.date
    df["货柜号"] = df["货柜号"].fillna("").astype(str).str.strip()
    df["部门"] = df["部门"].fillna(DEFAULT_DEPARTMENT).astype(str).str.strip()
    df["品类"] = df["品类"].fillna("").astype(str).str.strip()
    df["品牌"] = df["品牌"].fillna("").astype(str).str.strip()
    df["材质"] = df["材质"].fillna("180g").astype(str).str.strip()
    df["颜色"] = df["颜色"].astype(str).str.strip()
    df["成本"] = pd.to_numeric(df["成本"], errors="coerce").fillna(0)
    df["状态"] = df["状态"].fillna("未到货").astype(str).str.strip()
    df["备注"] = df["备注"].fillna("").astype(str).str.strip()
    df.loc[~df["状态"].isin(CONTAINER_STATUSES), "状态"] = "未到货"
    for size in SIZE_COLUMNS:
        df[size] = pd.to_numeric(df[size], errors="coerce").fillna(0).astype(int)

    df = df.dropna(subset=["预计到货日期"])
    df = df[(df["部门"] != "") & (df["材质"] != "") & (df["颜色"] != "")]
    detail_df = df.melt(
        id_vars=["预计到货日期", "货柜号", "部门", "品类", "品牌", "材质", "颜色", "成本", "状态", "备注"],
        value_vars=SIZE_COLUMNS,
        var_name="尺码",
        value_name="数量",
    )
    detail_df = detail_df[detail_df["数量"] > 0]
    return detail_df[
        ["预计到货日期", "货柜号", "部门", "品类", "品牌", "材质", "颜色", "尺码", "数量", "成本", "状态", "备注"]
    ].reset_index(drop=True)


def create_inventory_containers(supabase, df):
    records = []
    for row in normalize_container_rows(df).to_dict("records"):
        records.append({
            "expected_arrival_date": row["预计到货日期"].isoformat(),
            "container_no": row["货柜号"] or None,
            "department": row["部门"],
            "category": row["品类"] or None,
            "brand": row["品牌"],
            "material": row["材质"],
            "color": row["颜色"],
            "size": row["尺码"],
            "quantity": int(row["数量"]),
            "unit_cost": float(row["成本"] or 0),
            "品牌": row["品牌"],
            "材质": row["材质"],
            "成本": float(row["成本"] or 0),
            "status": row["状态"],
            "note": row["备注"] or None,
        })

    if not records:
        return []

    response = supabase.table("inventory_container_imports").insert(records).execute()
    return response.data


def build_container_display(df):
    if df.empty:
        return pd.DataFrame(columns=[
            "批次标识", "预计到货日期", "货柜号", "部门", "品类", "品牌", "材质", "颜色",
            *SIZE_COLUMNS, "总件数", "状态", "备注",
        ])

    display_df = df.copy()
    display_df["expected_arrival_date"] = pd.to_datetime(
        display_df["expected_arrival_date"], errors="coerce"
    ).dt.date
    display_df["container_no"] = display_df["container_no"].fillna("")
    display_df["category"] = display_df["category"].fillna("")
    display_df["department"] = display_df["department"].fillna(DEFAULT_DEPARTMENT)
    display_df["brand"] = display_df["brand"].fillna("")
    display_df["material"] = display_df["material"].fillna("")
    display_df["note"] = display_df["note"].fillna("")
    pivot_df = (
        display_df
        .pivot_table(
            index=[
                "expected_arrival_date", "container_no", "department", "category", "brand",
                "material", "color", "status", "note",
            ],
            columns="size",
            values="quantity",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
    )
    for size in SIZE_COLUMNS:
        if size not in pivot_df.columns:
            pivot_df[size] = 0
        pivot_df[size] = pd.to_numeric(pivot_df[size], errors="coerce").fillna(0).astype(int)

    pivot_df["总件数"] = pivot_df[SIZE_COLUMNS].sum(axis=1)
    pivot_df = pivot_df.rename(columns={
        "expected_arrival_date": "预计到货日期",
        "container_no": "货柜号",
        "department": "部门",
        "category": "品类",
        "brand": "品牌",
        "material": "材质",
        "color": "颜色",
        "status": "状态",
        "note": "备注",
    })
    pivot_df["货柜号"] = pivot_df["货柜号"].fillna("").astype(str)
    pivot_df["备注"] = pivot_df["备注"].fillna("")
    pivot_df["批次标识"] = pivot_df.apply(
        lambda row: row["货柜号"] or f"{row['预计到货日期']}-{row['总件数']}",
        axis=1,
    )
    return pivot_df[[
        "批次标识", "预计到货日期", "货柜号", "部门", "品类", "品牌", "材质", "颜色",
        *SIZE_COLUMNS, "总件数", "状态", "备注",
    ]]
