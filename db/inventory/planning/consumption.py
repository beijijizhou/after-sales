import pandas as pd

from db.inventory import SIZE_COLUMNS


HALOO_CONSUMPTION_MODEL = "Haloo 15000订单消耗"
COLOR_ORDER = ["黑", "白"]
DEFAULT_ORDER_QUANTITY = 15000


def load_consumption_model(supabase, category, model_name=HALOO_CONSUMPTION_MODEL):
    response = (
        supabase
        .table("inventory_consumption_models")
        .select("model_name,category,client,brand,order_quantity,color,size,consumption_quantity")
        .eq("category", category)
        .eq("model_name", model_name)
        .execute()
    )
    return pd.DataFrame(response.data)


def scale_consumption_model(model_df, target_order_quantity=DEFAULT_ORDER_QUANTITY):
    if model_df.empty:
        return model_df.copy()

    scaled_df = model_df.copy()
    base_quantity = pd.to_numeric(
        scaled_df["order_quantity"],
        errors="coerce",
    ).dropna()
    base_quantity = int(base_quantity.iloc[0]) if not base_quantity.empty else DEFAULT_ORDER_QUANTITY
    if base_quantity <= 0:
        base_quantity = DEFAULT_ORDER_QUANTITY

    ratio = target_order_quantity / base_quantity
    scaled_df["consumption_quantity"] = (
        pd.to_numeric(scaled_df["consumption_quantity"], errors="coerce")
        .fillna(0)
        .mul(ratio)
        .round()
        .astype(int)
    )
    scaled_df["order_quantity"] = int(target_order_quantity)
    return scaled_df


def build_consumption_forecast(inventory_df, model_df):
    if inventory_df.empty or model_df.empty:
        return pd.DataFrame()

    model_df = model_df.copy()
    target_brand = str(model_df["brand"].dropna().iloc[0] if "brand" in model_df else "").strip()
    stock_df = inventory_df.copy()
    if target_brand and "品牌" in stock_df.columns:
        stock_df = stock_df[stock_df["品牌"].fillna("").astype(str).str.strip() == target_brand]

    stock_rows = []
    for _, row in stock_df.iterrows():
        for size in SIZE_COLUMNS:
            stock_rows.append({
                "颜色": row["颜色"],
                "尺码": size,
                "当前库存": int(row.get(size, 0) or 0),
            })

    stock_by_size = (
        pd.DataFrame(stock_rows)
        .groupby(["颜色", "尺码"], as_index=False)
        .agg(当前库存=("当前库存", "sum"))
    )
    demand_df = model_df.rename(columns={
        "color": "颜色",
        "size": "尺码",
        "consumption_quantity": "单轮消耗",
        "order_quantity": "订单量",
    })
    forecast_df = demand_df.merge(stock_by_size, on=["颜色", "尺码"], how="left")
    forecast_df["当前库存"] = forecast_df["当前库存"].fillna(0).astype(int)
    forecast_df["单轮消耗"] = forecast_df["单轮消耗"].astype(int)
    forecast_df["可支撑轮数"] = forecast_df["当前库存"] / forecast_df["单轮消耗"]
    forecast_df["剩余天数"] = forecast_df["可支撑轮数"].round().astype(int)
    forecast_df["可支撑订单量"] = (forecast_df["可支撑轮数"] * forecast_df["订单量"]).astype(int)
    forecast_df["下轮缺口"] = (forecast_df["单轮消耗"] - forecast_df["当前库存"]).clip(lower=0).astype(int)
    forecast_df["颜色"] = pd.Categorical(forecast_df["颜色"], categories=COLOR_ORDER, ordered=True)
    forecast_df["尺码"] = pd.Categorical(forecast_df["尺码"], categories=SIZE_COLUMNS, ordered=True)
    return (
        forecast_df[["颜色", "尺码", "当前库存", "单轮消耗", "剩余天数", "下轮缺口"]]
        .sort_values(["颜色", "尺码"])
        .reset_index(drop=True)
    )


def build_consumption_wide_table(forecast_df):
    if forecast_df.empty:
        return pd.DataFrame(columns=["颜色", "项目", *SIZE_COLUMNS])

    rows = []
    metric_names = {
        "当前库存": "当前库存",
        "单轮消耗": "1.5万单消耗",
        "剩余天数": "剩余天数",
        "下轮缺口": "下轮缺口",
    }
    for color in COLOR_ORDER:
        color_df = forecast_df[forecast_df["颜色"].astype(str) == color]
        if color_df.empty:
            continue

        for source_name, display_name in metric_names.items():
            row = {"颜色": color, "项目": display_name}
            values = color_df.set_index("尺码")[source_name].to_dict()
            for size in SIZE_COLUMNS:
                row[size] = int(values.get(size, 0) or 0)
            rows.append(row)

    return pd.DataFrame(rows, columns=["颜色", "项目", *SIZE_COLUMNS])


def build_consumption_model_table(model_df):
    if model_df.empty:
        return pd.DataFrame(columns=["颜色", *SIZE_COLUMNS])

    model_df = model_df.rename(columns={
        "color": "颜色",
        "size": "尺码",
        "consumption_quantity": "消耗数量",
    })
    display_df = (
        model_df
        .pivot_table(index="颜色", columns="尺码", values="消耗数量", fill_value=0)
        .reset_index()
    )
    for size in SIZE_COLUMNS:
        if size not in display_df.columns:
            display_df[size] = 0
        display_df[size] = pd.to_numeric(display_df[size], errors="coerce").fillna(0).astype(int)

    display_df["_color_order"] = display_df["颜色"].map({"黑": 0, "白": 1}).fillna(99)
    return (
        display_df[["颜色", *SIZE_COLUMNS, "_color_order"]]
        .sort_values(["_color_order", "颜色"], kind="stable")
        .drop(columns=["_color_order"])
        .reset_index(drop=True)
    )
