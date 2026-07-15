from datetime import timedelta

from db.inventory import SIZE_COLUMNS


def build_inventory_consumption_alerts(
    inventory_df,
    model_df,
    alert_days=14,
    coverage_days=None,
    inventory_date=None,
    current_date=None,
):
    if inventory_df.empty or model_df.empty:
        return inventory_df.copy()

    stock_df = inventory_df.groupby("颜色", as_index=False)[SIZE_COLUMNS].sum()
    model_df = model_df.rename(columns={
        "color": "颜色",
        "size": "尺码",
        "consumption_quantity": "消耗数量",
    })

    alert_by_color = {}
    elapsed_days = max((current_date - inventory_date).days, 0) if inventory_date and current_date else 0
    for _, stock_row in stock_df.iterrows():
        color = stock_row["颜色"]
        color_model = model_df[model_df["颜色"] == color]
        model_days_by_size = {}
        days_by_size = {}

        for size in SIZE_COLUMNS:
            consumption = color_model[color_model["尺码"] == size]["消耗数量"]
            if consumption.empty or int(consumption.iloc[0]) <= 0:
                continue
            model_days = round(int(stock_row[size]) / int(consumption.iloc[0]))
            model_days_by_size[size] = model_days
            days_by_size[size] = max(model_days - elapsed_days, 0)

        adjusted_coverage_days = (
            int(coverage_days) + elapsed_days if coverage_days is not None else None
        )
        shortage_by_size = build_shortage_by_size(
            color_model, stock_row, adjusted_coverage_days
        )
        minimum_days = min(days_by_size.values()) if days_by_size else None
        minimum_model_days = min(model_days_by_size.values()) if model_days_by_size else None
        alert_by_color[color] = {
            "库存基准日期": inventory_date,
            "当前日期": current_date,
            "最低剩余天数": minimum_days,
            "预计最早耗尽日期": (
                inventory_date + timedelta(days=minimum_model_days)
                if inventory_date and minimum_model_days is not None
                else None
            ),
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
    result_df["库存基准日期"] = result_df["颜色"].map(
        lambda color: alert_by_color.get(color, {}).get("库存基准日期")
    )
    result_df["当前日期"] = result_df["颜色"].map(
        lambda color: alert_by_color.get(color, {}).get("当前日期")
    )
    result_df["预计最早耗尽日期"] = result_df["颜色"].map(
        lambda color: alert_by_color.get(color, {}).get("预计最早耗尽日期")
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
    for column in ["库存基准日期", "当前日期", "最低剩余天数", "预计最早耗尽日期", "低于14天尺码"]:
        columns.remove(column)
    planning_columns = []
    if coverage_days is not None:
        planning_columns = ["到货前需覆盖天数", "到货前缺口总数", "到货前缺口尺码"]
        for column in planning_columns:
            columns.remove(column)
    insert_at = columns.index("颜色") + 1 if "颜色" in columns else 0
    return result_df[
        columns[:insert_at]
        + ["库存基准日期", "当前日期", "最低剩余天数", "预计最早耗尽日期", "低于14天尺码"]
        + planning_columns
        + columns[insert_at:]
    ]
