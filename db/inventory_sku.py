from datetime import date

import pandas as pd

from db.inventory import (
    DEFAULT_CATEGORY,
    DEFAULT_DEPARTMENT,
    SIZE_COLUMNS,
    create_inventory_snapshot,
)


def load_sku_imports(supabase, department=DEFAULT_DEPARTMENT, category=DEFAULT_CATEGORY, limit=200):
    query = (
        supabase
        .table("inventory_sku_imports")
        .select("department,category,brand,material,color,size,initial_quantity,unit_cost,import_date,created_at")
        .eq("department", department)
    )
    if category:
        query = query.eq("category", category)
    response = (
        query
        .order("import_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return pd.DataFrame(response.data)


def create_inventory_item(supabase, department, category, brand, material, color, size, quantity=0, unit_cost=0, import_date=None):
    department = str(department).strip()
    category = None if pd.isna(category) or str(category).strip() == "" else str(category).strip()
    brand = "" if pd.isna(brand) else str(brand).strip()
    material = str(material).strip()
    color = str(color).strip()
    size = str(size).strip().upper()
    quantity = int(quantity)
    unit_cost = float(unit_cost or 0)
    import_date = import_date or date.today()
    response = (
        supabase
        .table("inventory_items")
        .insert(
            {
                "department": department,
                "category": category,
                "brand": brand,
                "material": material,
                "color": color,
                "size": size,
                "unit_cost": unit_cost,
                "quantity": quantity,
                "品牌": brand,
                "材质": material,
                "成本": unit_cost,
            }
        )
        .execute()
    )
    try:
        supabase.table("inventory_sku_imports").insert({
            "department": department,
            "category": category,
            "brand": brand,
            "material": material,
            "color": color,
            "size": size,
            "initial_quantity": quantity,
            "unit_cost": unit_cost,
            "品牌": brand,
            "材质": material,
            "成本": unit_cost,
            "import_date": import_date.isoformat(),
        }).execute()
    except Exception as e:
        if "inventory_sku_imports" in str(e):
            raise RuntimeError("请先在 Supabase SQL Editor 运行库存 SQL 更新文件") from e
        raise
    return response.data


def build_sku_template():
    return pd.DataFrame(columns=["日期", "品牌", "材质", "颜色", "成本", *SIZE_COLUMNS])


def group_sku_rows(df):
    return (
        df
        .groupby(["日期", "品牌", "材质", "颜色", "尺码", "成本"], as_index=False)
        .agg(初始库存=("初始库存", "sum"))
    )


def normalize_sku_rows(df):
    column_map = {str(column).strip().upper(): column for column in df.columns}
    rename_map = {
        column_map[size.upper()]: size
        for size in SIZE_COLUMNS
        if size.upper() in column_map
    }
    if "日期" in df.columns:
        rename_map["日期"] = "日期"
    if "品牌" in df.columns:
        rename_map["品牌"] = "品牌"
    if "材质" in df.columns:
        rename_map["材质"] = "材质"
    if "克重" in df.columns:
        rename_map["克重"] = "材质"
    if "颜色" in df.columns:
        rename_map["颜色"] = "颜色"
    if "成本" in df.columns:
        rename_map["成本"] = "成本"
    if "更新库存" in df.columns:
        rename_map["更新库存"] = "更新库存"
    df = df.rename(columns=rename_map)

    df = df.copy()
    if {"尺码", "更新库存"}.issubset(df.columns):
        if "日期" not in df.columns:
            df["日期"] = date.today()
        if "品牌" not in df.columns:
            df["品牌"] = ""
        if "成本" not in df.columns:
            df["成本"] = 0
        required_columns = {"日期", "材质", "颜色", "尺码", "更新库存"}
        missing_columns = required_columns - set(df.columns)
        if missing_columns:
            raise ValueError(f"缺少列：{', '.join(sorted(missing_columns))}")
        df["日期"] = pd.to_datetime(df["日期"], errors="coerce").dt.date
        df["品牌"] = df["品牌"].fillna("").astype(str).str.strip()
        df["材质"] = df["材质"].fillna("180g").astype(str).str.strip()
        df["颜色"] = df["颜色"].astype(str).str.strip()
        df["尺码"] = df["尺码"].astype(str).str.strip().str.upper()
        df["成本"] = pd.to_numeric(df["成本"], errors="coerce").fillna(0)
        quantity_values = df["更新库存"].astype(str).str.replace(",", "", regex=False)
        df["初始库存"] = pd.to_numeric(quantity_values, errors="coerce").fillna(0).astype(int)
        df = df.dropna(subset=["日期"])
        df = df[(df["材质"] != "") & (df["颜色"] != "") & (df["尺码"].isin(SIZE_COLUMNS))]
        df = df[df["初始库存"] >= 0]
        return group_sku_rows(df[["日期", "品牌", "材质", "颜色", "尺码", "成本", "初始库存"]]).reset_index(drop=True)

    if "日期" not in df.columns:
        df["日期"] = date.today()
    if "品牌" not in df.columns:
        df["品牌"] = ""
    if "成本" not in df.columns:
        df["成本"] = 0
    required_columns = {"日期", "材质", "颜色", *SIZE_COLUMNS}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"缺少列：{', '.join(sorted(missing_columns))}")

    df["日期"] = pd.to_datetime(df["日期"], errors="coerce").dt.date
    df["品牌"] = df["品牌"].fillna("").astype(str).str.strip()
    df["材质"] = df["材质"].fillna("180g").astype(str).str.strip()
    df["颜色"] = df["颜色"].astype(str).str.strip()
    df["成本"] = pd.to_numeric(df["成本"], errors="coerce").fillna(0)
    for size in SIZE_COLUMNS:
        df[size] = pd.to_numeric(df[size], errors="coerce").fillna(0).astype(int)

    df = df.dropna(subset=["日期"])
    df = df[(df["材质"] != "") & (df["颜色"] != "")]
    sku_df = df.melt(
        id_vars=["日期", "品牌", "材质", "颜色", "成本"],
        value_vars=SIZE_COLUMNS,
        var_name="尺码",
        value_name="初始库存",
    )
    sku_df = sku_df[sku_df["初始库存"] >= 0]
    return group_sku_rows(sku_df[["日期", "品牌", "材质", "颜色", "尺码", "成本", "初始库存"]]).reset_index(drop=True)


def parse_sku_file(uploaded_file):
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    return normalize_sku_rows(df)


def apply_sku_rows(supabase, department, category, df):
    for row in df.to_dict("records"):
        create_inventory_item(
            supabase=supabase,
            department=department,
            category=category,
            brand=row["品牌"],
            material=row["材质"],
            color=row["颜色"],
            size=row["尺码"],
            quantity=row["初始库存"],
            unit_cost=row["成本"],
            import_date=row["日期"],
        )
    for import_date in sorted(df["日期"].dropna().unique()):
        create_inventory_snapshot(supabase, department, category, import_date)
