import pandas as pd


def build_finance_overview(finance_df):
    inbound = _direction_rows(finance_df, "入库")
    outbound = _direction_rows(finance_df, "出库")
    return {
        "inbound_quantity": _sum(inbound, "quantity"),
        "inbound_amount": _sum(inbound, "amount"),
        "outbound_quantity": _sum(outbound, "quantity"),
        "outbound_amount": _sum(outbound, "amount"),
        "missing_inbound_quantity": _missing_quantity(inbound),
        "missing_outbound_quantity": _missing_quantity(outbound),
    }


def build_department_summary(finance_df):
    columns = [
        "部门", "品类", "入库数量", "入库金额",
        "出库数量", "出库成本", "库存数量净变动", "成本净增加",
    ]
    if finance_df.empty:
        return pd.DataFrame(columns=columns)

    keys = ["department", "category"]
    grouped = (
        finance_df.assign(category=finance_df["category"].fillna(""))
        .groupby([*keys, "direction"], dropna=False)[["quantity", "amount"]]
        .sum()
        .reset_index()
    )
    inbound = _summary_side(grouped, keys, "入库", "inbound")
    outbound = _summary_side(grouped, keys, "出库", "outbound")
    result = inbound.merge(outbound, on=keys, how="outer").fillna(0)
    result["net_quantity"] = (
        result["inbound_quantity"] - result["outbound_quantity"]
    )
    result["net_amount"] = result["inbound_amount"] - result["outbound_amount"]
    return result.rename(columns={
        "department": "部门",
        "category": "品类",
        "inbound_quantity": "入库数量",
        "inbound_amount": "入库金额",
        "outbound_quantity": "出库数量",
        "outbound_amount": "出库成本",
        "net_quantity": "库存数量净变动",
        "net_amount": "成本净增加",
    })[columns].sort_values(
        ["出库成本", "入库金额"], ascending=False
    ).reset_index(drop=True)


def build_daily_summary(finance_df):
    columns = ["日期", "入库数量", "出库数量", "入库金额", "出库成本"]
    if finance_df.empty:
        return pd.DataFrame(columns=columns)
    grouped = (
        finance_df.groupby(["date", "direction"])[["quantity", "amount"]]
        .sum()
        .reset_index()
    )
    inbound = _summary_side(grouped, ["date"], "入库", "inbound")
    outbound = _summary_side(grouped, ["date"], "出库", "outbound")
    result = inbound.merge(outbound, on="date", how="outer").fillna(0)
    return result.rename(columns={
        "date": "日期",
        "inbound_quantity": "入库数量",
        "inbound_amount": "入库金额",
        "outbound_quantity": "出库数量",
        "outbound_amount": "出库成本",
    })[columns].sort_values("日期").reset_index(drop=True)


def build_container_summary(container_df):
    columns = [
        "货柜号", "预计到货日期", "实际到货日期", "状态",
        "部门", "品类", "数量", "采购金额", "缺成本件数",
    ]
    if container_df.empty:
        return pd.DataFrame(columns=columns)

    data = container_df.copy()
    data["container_no"] = data["container_no"].fillna("").where(
        data["container_no"].fillna("") != "", data["container_key"]
    )
    data["missing_quantity"] = data["quantity"].where(
        data["missing_cost"], 0
    )
    keys = [
        "container_key", "container_no", "expected_arrival_date",
        "actual_arrival_date", "status", "department", "category",
    ]
    result = (
        data.groupby(keys, dropna=False)[
            ["quantity", "amount", "missing_quantity"]
        ]
        .sum()
        .reset_index()
        .rename(columns={
            "container_no": "货柜号",
            "expected_arrival_date": "预计到货日期",
            "actual_arrival_date": "实际到货日期",
            "status": "状态",
            "department": "部门",
            "category": "品类",
            "quantity": "数量",
            "amount": "采购金额",
            "missing_quantity": "缺成本件数",
        })
    )
    return result[columns].sort_values(
        ["预计到货日期", "货柜号"]
    ).reset_index(drop=True)


def _direction_rows(finance_df, direction):
    if finance_df.empty:
        return finance_df
    return finance_df[finance_df["direction"] == direction]


def _sum(df, column):
    if df.empty:
        return 0
    return float(pd.to_numeric(df[column], errors="coerce").fillna(0).sum())


def _missing_quantity(df):
    if df.empty:
        return 0
    return int(df.loc[df["missing_cost"], "quantity"].sum())


def _summary_side(grouped, keys, direction, prefix):
    side = grouped[grouped["direction"] == direction][
        [*keys, "quantity", "amount"]
    ].copy()
    return side.rename(columns={
        "quantity": f"{prefix}_quantity",
        "amount": f"{prefix}_amount",
    })
