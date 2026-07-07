import pandas as pd


CATEGORY = "彩色 T-shirt"
SIZE_COLUMNS = ["S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]


def load_inventory_items(supabase):
    response = (
        supabase
        .table("inventory_items")
        .select("category,材质,color,size,quantity,updated_at")
        .eq("category", CATEGORY)
        .execute()
    )
    return pd.DataFrame(response.data)


def load_inventory_movements(supabase, limit=20):
    response = (
        supabase
        .table("inventory_movements")
        .select("材质,color,size,quantity_change,quantity_after,movement_date,reason,created_at")
        .eq("category", CATEGORY)
        .order("movement_date", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return pd.DataFrame(response.data)


def adjust_inventory(supabase, material, color, size, quantity_change, reason, movement_date):
    response = (
        supabase
        .rpc(
            "adjust_inventory_stock",
            {
                "p_category": CATEGORY,
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
    return pd.DataFrame(columns=["日期", "操作", "材质", "颜色", "尺码", "数量", "备注"])


def build_wide_adjustment_template():
    return pd.DataFrame(columns=["日期", "材质", "颜色", *SIZE_COLUMNS, "备注"])


def normalize_wide_adjustment_rows(df):
    required_columns = {"日期", "操作", "材质", "颜色", *SIZE_COLUMNS}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"缺少列：{', '.join(sorted(missing_columns))}")

    df = df.copy()
    df["日期"] = pd.to_datetime(df["日期"], errors="coerce").dt.date
    df["操作"] = df["操作"].astype(str).str.strip()
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
        id_vars=["日期", "操作", "材质", "颜色", "备注"],
        value_vars=SIZE_COLUMNS,
        var_name="尺码",
        value_name="数量",
    )
    adjustment_df = adjustment_df[adjustment_df["数量"] > 0]
    return adjustment_df[["日期", "操作", "材质", "颜色", "尺码", "数量", "备注"]].reset_index(drop=True)


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
    return df[["日期", "操作", "材质", "颜色", "尺码", "数量", "备注"]].reset_index(drop=True)


def parse_adjustment_file(uploaded_file):
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    return normalize_adjustment_rows(df)


def apply_adjustment_rows(supabase, df):
    for row in df.to_dict("records"):
        quantity_change = int(row["数量"]) if row["操作"] == "增加" else -int(row["数量"])
        adjust_inventory(
            supabase=supabase,
            material=row["材质"],
            color=row["颜色"],
            size=row["尺码"],
            quantity_change=quantity_change,
            reason=row["备注"],
            movement_date=row["日期"],
        )


def build_inventory_table(df):
    if df.empty:
        return pd.DataFrame(columns=["材质", "颜色", "总库存", *SIZE_COLUMNS])

    pivot_df = (
        df
        .pivot_table(index=["材质", "color"], columns="size", values="quantity", fill_value=0)
        .reset_index()
        .rename(columns={"color": "颜色"})
    )
    for size in SIZE_COLUMNS:
        if size not in pivot_df.columns:
            pivot_df[size] = 0

    pivot_df["总库存"] = pivot_df[SIZE_COLUMNS].sum(axis=1)
    return pivot_df[["材质", "颜色", "总库存", *SIZE_COLUMNS]].sort_values("总库存", ascending=False)


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
