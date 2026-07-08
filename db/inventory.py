import pandas as pd


DEFAULT_CATEGORY = "黑白短袖"
CATEGORY = DEFAULT_CATEGORY
INVENTORY_CATEGORIES = ["彩色短袖", "黑白短袖", "卫衣"]
SIZE_COLUMNS = ["S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]
BLACK_WHITE_MATERIAL_ORDER = {"180g": 0, "160g": 1, "CVC": 2}
BLACK_WHITE_COLOR_ORDER = {"黑": 0, "白": 1}


def load_inventory_items(supabase, category=DEFAULT_CATEGORY):
    response = (
        supabase
        .table("inventory_items")
        .select("category,品牌,材质,color,size,成本,quantity,updated_at")
        .eq("category", category)
        .execute()
    )
    return pd.DataFrame(response.data)


def load_inventory_movements(supabase, category=DEFAULT_CATEGORY, limit=20):
    response = (
        supabase
        .table("inventory_movements")
        .select("品牌,材质,color,size,quantity_change,quantity_after,movement_date,reason,created_at")
        .eq("category", category)
        .order("movement_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return pd.DataFrame(response.data)


def adjust_inventory(supabase, category, brand, material, color, size, quantity_change, reason, movement_date):
    response = (
        supabase
        .rpc(
            "adjust_inventory_stock",
            {
                "p_category": category,
                "p_brand": brand,
                "p_material": material,
                "p_color": color,
                "p_size": size,
                "p_quantity_change": quantity_change,
                "p_reason": reason,
                "p_movement_date": movement_date.isoformat(),
            }
        )
        .execute()
    )
    return response.data


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
    for size in SIZE_COLUMNS:
        df[size] = pd.to_numeric(df[size], errors="coerce").fillna(0).astype(int)

    df = df.dropna(subset=["日期"])
    df = df[(df["材质"] != "") & (df["颜色"] != "") & (df["操作"].isin(["增加", "扣减"]))]
    adjustment_df = df.melt(
        id_vars=["日期", "操作", "品牌", "材质", "颜色", "备注"],
        value_vars=SIZE_COLUMNS,
        var_name="尺码",
        value_name="数量",
    )
    adjustment_df = adjustment_df[adjustment_df["数量"] > 0]
    return adjustment_df[["日期", "操作", "品牌", "材质", "颜色", "尺码", "数量", "备注"]].reset_index(drop=True)


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

    df = df.dropna(subset=["日期"])
    df = df[df["数量"] > 0]
    df = df[df["操作"].isin(["增加", "扣减"])]
    df = df[df["材质"] != ""]
    df = df[df["尺码"].isin(SIZE_COLUMNS)]
    return df[["日期", "操作", "品牌", "材质", "颜色", "尺码", "数量", "备注"]].reset_index(drop=True)


def parse_adjustment_file(uploaded_file):
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    return normalize_adjustment_rows(df)


def apply_adjustment_rows(supabase, category, df):
    for row in df.to_dict("records"):
        quantity_change = int(row["数量"]) if row["操作"] == "增加" else -int(row["数量"])
        adjust_inventory(
            supabase=supabase,
            category=category,
            brand=row["品牌"],
            material=row["材质"],
            color=row["颜色"],
            size=row["尺码"],
            quantity_change=quantity_change,
            reason=row["备注"],
            movement_date=row["日期"],
        )


def sort_inventory_table(df, category):
    if category != "黑白短袖" or df.empty:
        return df.sort_values("总库存", ascending=False)

    sorted_df = df.copy()
    sorted_df["_material_order"] = sorted_df["材质"].map(BLACK_WHITE_MATERIAL_ORDER).fillna(99)
    sorted_df["_color_order"] = sorted_df["颜色"].map(BLACK_WHITE_COLOR_ORDER).fillna(99)
    sorted_df = sorted_df.sort_values(
        ["_material_order", "_color_order", "品牌", "成本"],
        kind="stable",
    )
    return sorted_df.drop(columns=["_material_order", "_color_order"])


def build_inventory_table(df, category=DEFAULT_CATEGORY):
    if df.empty:
        return pd.DataFrame(columns=["品牌", "材质", "颜色", "成本", *SIZE_COLUMNS, "总库存"])

    inventory_df = df.copy()
    if "成本" not in inventory_df.columns:
        inventory_df["成本"] = 0
    if "品牌" not in inventory_df.columns:
        inventory_df["品牌"] = ""
    inventory_df["品牌"] = inventory_df["品牌"].fillna("").astype(str)
    inventory_df["成本"] = pd.to_numeric(inventory_df["成本"], errors="coerce").fillna(0)
    pivot_df = (
        inventory_df
        .pivot_table(index=["品牌", "材质", "color", "成本"], columns="size", values="quantity", fill_value=0)
        .reset_index()
        .rename(columns={"color": "颜色"})
    )
    for size in SIZE_COLUMNS:
        if size not in pivot_df.columns:
            pivot_df[size] = 0
        pivot_df[size] = pd.to_numeric(pivot_df[size], errors="coerce").fillna(0).astype(int)

    pivot_df["总库存"] = pivot_df[SIZE_COLUMNS].sum(axis=1)
    display_df = pivot_df[["品牌", "材质", "颜色", "成本", *SIZE_COLUMNS, "总库存"]]
    return sort_inventory_table(display_df, category).reset_index(drop=True)


def build_color_inventory_table(inventory_df):
    if inventory_df.empty:
        return pd.DataFrame(columns=["颜色", *SIZE_COLUMNS, "总库存"])

    color_df = (
        inventory_df
        .groupby("颜色", as_index=False)[SIZE_COLUMNS]
        .sum()
    )
    for size in SIZE_COLUMNS:
        color_df[size] = pd.to_numeric(color_df[size], errors="coerce").fillna(0).astype(int)
    color_df["总库存"] = color_df[SIZE_COLUMNS].sum(axis=1)
    color_df["_color_order"] = color_df["颜色"].map(BLACK_WHITE_COLOR_ORDER).fillna(99)
    return (
        color_df[["颜色", *SIZE_COLUMNS, "总库存", "_color_order"]]
        .sort_values(["_color_order", "颜色"], kind="stable")
        .drop(columns=["_color_order"])
        .reset_index(drop=True)
    )


def build_daily_movement_summary(df):
    if df.empty or "movement_date" not in df.columns:
        return pd.DataFrame(columns=["日期", "入库", "消耗", "净变动"])

    movement_df = df.copy()
    movement_df["inbound"] = movement_df["quantity_change"].clip(lower=0)
    movement_df["outbound"] = movement_df["quantity_change"].clip(upper=0).abs()
    summary = (
        movement_df
        .groupby("movement_date", as_index=False)
        .agg(
            inbound=("inbound", "sum"),
            outbound=("outbound", "sum"),
            net_change=("quantity_change", "sum"),
        )
        .rename(columns={
            "movement_date": "日期",
            "inbound": "入库",
            "outbound": "消耗",
            "net_change": "净变动",
        })
    )
    return summary.sort_values("日期", ascending=False).reset_index(drop=True)
