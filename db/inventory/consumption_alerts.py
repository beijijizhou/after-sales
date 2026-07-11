from db.inventory import SIZE_COLUMNS


def build_inventory_consumption_alerts(inventory_df, model_df, alert_days=14, coverage_days=None):
    if inventory_df.empty or model_df.empty:
        return inventory_df.copy()

    stock_df = inventory_df.groupby("颜色", as_index=False)[SIZE_COLUMNS].sum()
    model_df = model_df.rename(columns={
        "color": "颜色",
        "size": "尺码",
        "consumption_quantity": "消耗数量",
    })

    alert_by_color = {}
    for _, stock_row in stock_df.iterrows():
        color = stock_row["颜色"]
        color_model = model_df[model_df["颜色"] == color]
        days_by_size = {}

        for size in SIZE_COLUMNS:
            consumption = color_model[color_model["尺码"] == size]["消耗数量"]
            if consumption.empty or int(consumption.iloc[0]) <= 0:
                continue
            days_by_size[size] = round(int(stock_row[size]) / int(consumption.iloc[0]))

        shortage_by_size = build_shortage_by_size(color_model, stock_row, coverage_days)
        alert_by_color[color] = {
            "最低剩余天数": min(days_by_size.values()) if days_by_size else None,
            "低于14天尺码": build_low_stock_text(days_by_size, alert_days),
            "到货前需覆盖天数": int(coverage_days) if coverage_days is not None else None,
            "到货前缺口总数": sum(shortage_by_size.values()),
            "到货前缺口尺码": "，".join(
                f"{size}:{quantity}件"
                for size, quantity in shortage_by_size.items()
            ),
        }

    return attach_alert_columns(inventory_df, alert_by_color, coverage_days)


def build_low_stock_text(days_by_size, alert_days):
    return "，".join(
        f"{size}:{days}天"
        for size, days in days_by_size.items()
        if days < alert_days
    )


def build_shortage_by_size(color_model, stock_row, coverage_days):
    if coverage_days is None:
        return {}

    shortage_by_size = {}
    for size in SIZE_COLUMNS:
        consumption = color_model[color_model["尺码"] == size]["消耗数量"]
        if consumption.empty or int(consumption.iloc[0]) <= 0:
            continue

        required_quantity = int(consumption.iloc[0]) * int(coverage_days)
        shortage = max(required_quantity - int(stock_row[size]), 0)
        if shortage > 0:
            shortage_by_size[size] = shortage
    return shortage_by_size


def attach_alert_columns(inventory_df, alert_by_color, coverage_days):
    result_df = inventory_df.copy()
    result_df["最低剩余天数"] = result_df["颜色"].map(
        lambda color: alert_by_color.get(color, {}).get("最低剩余天数")
    )
    result_df["低于14天尺码"] = result_df["颜色"].map(
        lambda color: alert_by_color.get(color, {}).get("低于14天尺码", "")
    )
    if coverage_days is not None:
        result_df["到货前需覆盖天数"] = result_df["颜色"].map(
            lambda color: alert_by_color.get(color, {}).get("到货前需覆盖天数")
        )
        result_df["到货前缺口总数"] = result_df["颜色"].map(
            lambda color: alert_by_color.get(color, {}).get("到货前缺口总数", 0)
        )
        result_df["到货前缺口尺码"] = result_df["颜色"].map(
            lambda color: alert_by_color.get(color, {}).get("到货前缺口尺码", "")
        )

    columns = list(result_df.columns)
    for column in ["最低剩余天数", "低于14天尺码"]:
        columns.remove(column)
    planning_columns = []
    if coverage_days is not None:
        planning_columns = ["到货前需覆盖天数", "到货前缺口总数", "到货前缺口尺码"]
        for column in planning_columns:
            columns.remove(column)
    insert_at = columns.index("颜色") + 1 if "颜色" in columns else 0
    return result_df[
        columns[:insert_at]
        + ["最低剩余天数", "低于14天尺码"]
        + planning_columns
        + columns[insert_at:]
    ]
