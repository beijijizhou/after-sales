import pandas as pd

from db.inventory.constants import SIZE_COLUMNS
from db.inventory.snapshots import create_inventory_snapshot


def adjust_inventory(
    supabase,
    department,
    category,
    brand,
    material,
    color,
    size,
    quantity_change,
    reason,
    movement_date,
    unit_cost=None,
):
    params = {
        "p_department": department,
        "p_category": category,
        "p_brand": brand,
        "p_material": material,
        "p_color": color,
        "p_size": size,
        "p_quantity_change": quantity_change,
        "p_reason": reason,
        "p_movement_date": movement_date.isoformat(),
    }
    function_name = "adjust_inventory_stock"
    if unit_cost is not None:
        function_name = "adjust_inventory_stock_with_cost"
        params["p_unit_cost"] = float(unit_cost)

    response = supabase.rpc(function_name, params).execute()
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
    if "成本" not in df.columns:
        df["成本"] = pd.NA
    df["成本"] = pd.to_numeric(df["成本"], errors="coerce")
    for size in SIZE_COLUMNS:
        df[size] = pd.to_numeric(df[size], errors="coerce").fillna(0).astype(int)

    df = df.dropna(subset=["日期"])
    df = df[(df["材质"] != "") & (df["颜色"] != "") & (df["操作"].isin(["增加", "扣减"]))]
    adjustment_df = df.melt(
        id_vars=["日期", "操作", "品牌", "材质", "颜色", "成本", "备注"],
        value_vars=SIZE_COLUMNS,
        var_name="尺码",
        value_name="数量",
    )
    adjustment_df = adjustment_df[adjustment_df["数量"] > 0]
    columns = ["日期", "操作", "品牌", "材质", "颜色", "尺码", "数量", "成本", "备注"]
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
    df = df[df["操作"].isin(["增加", "扣减"])]
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


def apply_adjustment_rows(supabase, department, category, df):
    for row in df.to_dict("records"):
        quantity_change = int(row["数量"]) if row["操作"] == "增加" else -int(row["数量"])
        adjust_inventory(
            supabase=supabase,
            department=department,
            category=category,
            brand=row["品牌"],
            material=row["材质"],
            color=row["颜色"],
            size=row["尺码"],
            quantity_change=quantity_change,
            reason=row["备注"],
            movement_date=row["日期"],
            unit_cost=None if pd.isna(row.get("成本")) else row.get("成本"),
        )
    for movement_date in sorted(df["日期"].dropna().unique()):
        create_inventory_snapshot(supabase, department, category, movement_date)
