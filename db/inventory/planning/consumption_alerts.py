from datetime import timedelta

import pandas as pd

from db.inventory import SIZE_COLUMNS
from db.planning import calculate_stock_plan


def build_inventory_consumption_alerts(
    inventory_df,
    model_df,
    alert_days=14,
    coverage_days=None,
    inventory_date=None,
    current_date=None,
    sizes=None,
    target_days=None,
):
    if inventory_df.empty or model_df.empty:
        return inventory_df.copy()

    active_sizes = sizes or SIZE_COLUMNS
    model_df = model_df.rename(columns={
        "color": "颜色",
        "size": "尺码",
        "consumption_quantity": "消耗数量",
    })
    model_df["消耗数量"] = pd.to_numeric(
        model_df["消耗数量"], errors="coerce"
    ).fillna(0)
    model_df = (
        model_df.groupby(["颜色", "尺码"], as_index=False)["消耗数量"]
        .sum()
    )
    inventory_df = _append_demand_only_colors(inventory_df, model_df)
    stock_df = inventory_df.groupby("颜色", as_index=False)[SIZE_COLUMNS].sum()

    alert_by_color = {}
    elapsed_days = max((current_date - inventory_date).days, 0) if inventory_date and current_date else 0
    for _, stock_row in stock_df.iterrows():
        color = stock_row["颜色"]
        color_model = model_df[model_df["颜色"] == color]
        model_days_by_size = {}
        days_by_size = {}

        for size in active_sizes:
            consumption = color_model[color_model["尺码"] == size]["消耗数量"]
            if consumption.empty or int(consumption.iloc[0]) <= 0:
                continue
            plan = calculate_stock_plan(
                stock_row[size], consumption.iloc[0], elapsed_days=0
            )
            model_days = round(plan.coverage_days)
            model_days_by_size[size] = model_days
            days_by_size[size] = max(model_days - elapsed_days, 0)

        adjusted_coverage_days = (
            int(coverage_days) + elapsed_days if coverage_days is not None else None
        )
        shortage_by_size = build_shortage_by_size(
            color_model, stock_row, adjusted_coverage_days, active_sizes
        )
        stock_total = sum(int(stock_row[size]) for size in active_sizes)
        daily_total = sum(
            int(color_model.loc[
                color_model["尺码"] == size, "消耗数量"
            ].sum())
            for size in active_sizes
        )
        estimated_current_total = sum(
            calculate_stock_plan(
                stock_row[size],
                color_model.loc[
                    color_model["尺码"] == size, "消耗数量"
                ].sum(),
                elapsed_days=elapsed_days,
            ).estimated_current_quantity
            for size in active_sizes
        )
        minimum_days = min(days_by_size.values()) if days_by_size else None
        minimum_model_days = min(model_days_by_size.values()) if model_days_by_size else None
        reorder_by_size = build_reorder_by_size(
            color_model, stock_row, elapsed_days, target_days, active_sizes
        )
        alert_by_color[color] = {
            "库存基准日期": inventory_date,
            "当前日期": current_date,
            "库存基准总数": stock_total,
            "预计当前库存": estimated_current_total,
            "预测日耗合计": daily_total,
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
            "目标备货天数": (
                int(target_days) if target_days is not None else None
            ),
            "建议点货量": sum(reorder_by_size.values()),
            "建议点货尺码": "，".join(
                f"{size}:{quantity}件"
                for size, quantity in reorder_by_size.items()
            ),
        }

    return attach_alert_columns(inventory_df, alert_by_color, coverage_days)


def _append_demand_only_colors(inventory_df, model_df):
    stock_colors = set(inventory_df["颜色"].dropna().astype(str))
    demand_colors = set(model_df["颜色"].dropna().astype(str))
    missing = sorted(demand_colors - stock_colors)
    if not missing:
        return inventory_df
    rows = []
    for color in missing:
        row = {column: pd.NA for column in inventory_df.columns}
        row["颜色"] = color
        for size in SIZE_COLUMNS:
            row[size] = 0
        if "总库存" in row:
            row["总库存"] = 0
        rows.append(row)
    return pd.concat([inventory_df, pd.DataFrame(rows)], ignore_index=True)


def build_low_stock_text(days_by_size, alert_days):
    return "，".join(
        f"{size}:{days}天"
        for size, days in days_by_size.items()
        if days < alert_days
    )


def build_shortage_by_size(
    color_model, stock_row, coverage_days, sizes=None
):
    if coverage_days is None:
        return {}

    shortage_by_size = {}
    for size in sizes or SIZE_COLUMNS:
        consumption = color_model[color_model["尺码"] == size]["消耗数量"]
        if consumption.empty or int(consumption.iloc[0]) <= 0:
            continue

        plan = calculate_stock_plan(
            stock_row[size],
            consumption.iloc[0],
            target_days=coverage_days,
        )
        shortage = plan.reorder_quantity
        if shortage > 0:
            shortage_by_size[size] = shortage
    return shortage_by_size


def build_reorder_by_size(
    color_model, stock_row, elapsed_days, target_days, sizes=None,
):
    if target_days is None:
        return {}
    reorder = {}
    for size in sizes or SIZE_COLUMNS:
        consumption = pd.to_numeric(
            color_model.loc[
                color_model["尺码"] == size, "消耗数量"
            ], errors="coerce"
        ).fillna(0).sum()
        if consumption <= 0:
            continue
        plan = calculate_stock_plan(
            stock_row[size],
            consumption,
            target_days=target_days,
            elapsed_days=elapsed_days,
        )
        quantity = plan.reorder_quantity
        if quantity > 0:
            reorder[size] = int(quantity)
    return reorder


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
    for column in ["库存基准总数", "预计当前库存", "预测日耗合计"]:
        result_df[column] = result_df["颜色"].map(
            lambda color: alert_by_color.get(color, {}).get(column, 0)
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
    if any(
        alert.get("目标备货天数") is not None
        for alert in alert_by_color.values()
    ):
        for column, default in [
            ("目标备货天数", None),
            ("建议点货量", 0),
            ("建议点货尺码", ""),
        ]:
            result_df[column] = result_df["颜色"].map(
                lambda color, field=column, fallback=default: (
                    alert_by_color.get(color, {}).get(field, fallback)
                )
            )

    columns = list(result_df.columns)
    summary_columns = [
        "库存基准日期", "当前日期", "库存基准总数",
        "预计当前库存", "预测日耗合计", "最低剩余天数",
        "预计最早耗尽日期", "低于14天尺码",
    ]
    for column in summary_columns:
        columns.remove(column)
    planning_columns = []
    if coverage_days is not None:
        planning_columns = ["到货前需覆盖天数", "到货前缺口总数", "到货前缺口尺码"]
        for column in planning_columns:
            columns.remove(column)
    reorder_columns = [
        column for column in ["目标备货天数", "建议点货量", "建议点货尺码"]
        if column in columns
    ]
    for column in reorder_columns:
        columns.remove(column)
    insert_at = columns.index("颜色") + 1 if "颜色" in columns else 0
    return result_df[
        columns[:insert_at]
        + summary_columns
        + planning_columns
        + reorder_columns
        + columns[insert_at:]
    ]
