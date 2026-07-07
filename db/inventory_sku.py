from datetime import date

import pandas as pd

from db.inventory import CATEGORY, SIZE_COLUMNS


def load_sku_imports(supabase, limit=200):
    response = (
        supabase
        .table("inventory_sku_imports")
        .select("材质,color,size,initial_quantity,import_date,created_at")
        .eq("category", CATEGORY)
        .order("import_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return pd.DataFrame(response.data)


def create_inventory_item(supabase, material, color, size, quantity=0, import_date=None):
    material = str(material).strip()
    color = str(color).strip()
    size = str(size).strip().upper()
    quantity = int(quantity)
    import_date = import_date or date.today()
    response = (
        supabase
        .table("inventory_items")
        .upsert(
            {
                "category": CATEGORY,
                "材质": material,
                "color": color,
                "size": size,
                "quantity": quantity,
            },
            on_conflict="category,材质,color,size",
            ignore_duplicates=True,
        )
        .execute()
    )
    try:
        supabase.table("inventory_sku_imports").insert({
            "category": CATEGORY,
            "材质": material,
            "color": color,
            "size": size,
            "initial_quantity": quantity,
            "import_date": import_date.isoformat(),
        }).execute()
    except Exception as e:
        if "inventory_sku_imports" in str(e):
            raise RuntimeError("请先在 Supabase SQL Editor 运行 sql/add_inventory_sku_imports.sql") from e
        raise
    return response.data


def build_sku_template():
    return pd.DataFrame(columns=["日期", "材质", "颜色", *SIZE_COLUMNS])


def normalize_sku_rows(df):
    column_map = {str(column).strip().upper(): column for column in df.columns}
    rename_map = {
        column_map[size.upper()]: size
        for size in SIZE_COLUMNS
        if size.upper() in column_map
    }
    if "日期" in df.columns:
        rename_map["日期"] = "日期"
    if "材质" in df.columns:
        rename_map["材质"] = "材质"
    if "颜色" in df.columns:
        rename_map["颜色"] = "颜色"
    df = df.rename(columns=rename_map)

    required_columns = {"日期", "材质", "颜色", *SIZE_COLUMNS}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"缺少列：{', '.join(sorted(missing_columns))}")

    df = df.copy()
    df["日期"] = pd.to_datetime(df["日期"], errors="coerce").dt.date
    df["材质"] = df["材质"].fillna("180g").astype(str).str.strip()
    df["颜色"] = df["颜色"].astype(str).str.strip()
    for size in SIZE_COLUMNS:
        df[size] = pd.to_numeric(df[size], errors="coerce").fillna(0).astype(int)

    df = df.dropna(subset=["日期"])
    df = df[(df["材质"] != "") & (df["颜色"] != "")]
    sku_df = df.melt(
        id_vars=["日期", "材质", "颜色"],
        value_vars=SIZE_COLUMNS,
        var_name="尺码",
        value_name="初始库存",
    )
    sku_df = sku_df[sku_df["初始库存"] >= 0]
    return sku_df[["日期", "材质", "颜色", "尺码", "初始库存"]].drop_duplicates().reset_index(drop=True)


def parse_sku_file(uploaded_file):
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    return normalize_sku_rows(df)


def apply_sku_rows(supabase, df):
    for row in df.to_dict("records"):
        create_inventory_item(
            supabase=supabase,
            material=row["材质"],
            color=row["颜色"],
            size=row["尺码"],
            quantity=row["初始库存"],
            import_date=row["日期"],
        )
