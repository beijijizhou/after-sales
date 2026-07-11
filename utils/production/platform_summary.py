import pandas as pd

from utils.production.constants import HALOO_PLATFORM
from utils.production.normalization import get_person_working_hours, normalize_platform


def summarize_by_user(df, user_column):
    summary = (
        df
        .groupby(user_column, as_index=False)
        .agg(
            scan_count=("barcode", "size"),
            multiple_order_count=("is_multiple_order", "sum"),
        )
        .rename(columns={user_column: "name"})
    )
    return summary.sort_values("scan_count", ascending=False).reset_index(drop=True)


def build_person_platform_summary(df, user_column):
    pivot_df = (
        df
        .pivot_table(index=user_column, columns="platform", values="barcode", fill_value=0, aggfunc="size")
        .reset_index()
        .rename(columns={user_column: "人员"})
    )
    platform_columns = [column for column in pivot_df.columns if column != "人员"]
    pivot_df["总生产数量"] = pivot_df[platform_columns].sum(axis=1)
    multiple_orders = df.groupby(user_column, as_index=False)["is_multiple_order"].sum()
    multiple_orders = multiple_orders.rename(columns={user_column: "人员", "is_multiple_order": "多件订单数量"})
    pivot_df = pivot_df.merge(multiple_orders, on="人员", how="left")
    working_hours = get_person_working_hours(df, user_column)
    pivot_df = pivot_df.merge(working_hours.rename(columns={user_column: "人员"}), on="人员", how="left")
    return finalize_person_platform_summary(pivot_df, platform_columns)


def build_person_platform_summary_from_rpc(df):
    required_columns = {"person", "platform", "scan_count", "multiple_order_count", "first_scan_at", "last_scan_at"}
    if df.empty or not required_columns.issubset(df.columns):
        return pd.DataFrame()

    summary_df = df.copy()
    summary_df["platform"] = summary_df["platform"].apply(normalize_platform)
    summary_df["scan_count"] = pd.to_numeric(summary_df["scan_count"], errors="coerce").fillna(0).astype(int)
    summary_df["multiple_order_count"] = pd.to_numeric(
        summary_df["multiple_order_count"], errors="coerce"
    ).fillna(0).astype(int)
    pivot_df = (
        summary_df
        .pivot_table(index="person", columns="platform", values="scan_count", fill_value=0, aggfunc="sum")
        .reset_index()
        .rename(columns={"person": "人员"})
    )
    platform_columns = [column for column in pivot_df.columns if column != "人员"]
    pivot_df["总生产数量"] = pivot_df[platform_columns].sum(axis=1)
    pivot_df = pivot_df.merge(build_rpc_multiple_orders(summary_df), on="人员", how="left")
    pivot_df = pivot_df.merge(build_rpc_working_hours(summary_df), on="人员", how="left")
    return finalize_person_platform_summary(pivot_df, platform_columns)


def build_rpc_multiple_orders(summary_df):
    return (
        summary_df
        .groupby("person", as_index=False)["multiple_order_count"]
        .sum()
        .rename(columns={"person": "人员", "multiple_order_count": "多件订单数量"})
    )


def build_rpc_working_hours(summary_df):
    time_df = summary_df.copy()
    time_df["first_scan_at"] = pd.to_datetime(time_df["first_scan_at"], errors="coerce", utc=True)
    time_df["last_scan_at"] = pd.to_datetime(time_df["last_scan_at"], errors="coerce", utc=True)
    working_hours = (
        time_df
        .groupby("person", as_index=False)
        .agg(first_scan_at=("first_scan_at", "min"), last_scan_at=("last_scan_at", "max"))
    )
    working_hours["working_hours"] = (
        working_hours["last_scan_at"] - working_hours["first_scan_at"]
    ).dt.total_seconds() / 3600
    return working_hours.rename(columns={"person": "人员"})[["人员", "working_hours"]]


def finalize_person_platform_summary(pivot_df, platform_columns):
    pivot_df["时产量"] = (
        pivot_df["总生产数量"] / pivot_df["working_hours"]
    ).replace([float("inf"), -float("inf")], 0).fillna(0).round(1)
    if HALOO_PLATFORM not in pivot_df.columns:
        pivot_df[HALOO_PLATFORM] = 0
    pivot_df["Haloo 数量"] = pivot_df[HALOO_PLATFORM]
    pivot_df["Haloo 占比"] = (pivot_df["Haloo 数量"] / pivot_df["总生产数量"] * 100).fillna(0).round(1)
    detail_columns = [column for column in platform_columns if column != HALOO_PLATFORM]
    ordered_columns = [
        "人员", "总生产数量", "多件订单数量", "时产量",
        "Haloo 数量", "Haloo 占比", *detail_columns,
    ]
    return pivot_df[ordered_columns].sort_values("Haloo 占比", ascending=False).reset_index(drop=True)


def summarize_by_user_from_rpc(df):
    required_columns = {"person", "scan_count", "multiple_order_count", "first_scan_at", "last_scan_at"}
    if df.empty or not required_columns.issubset(df.columns):
        return pd.DataFrame()

    summary_df = df.copy()
    summary_df["scan_count"] = pd.to_numeric(summary_df["scan_count"], errors="coerce").fillna(0).astype(int)
    summary_df["multiple_order_count"] = pd.to_numeric(
        summary_df["multiple_order_count"], errors="coerce"
    ).fillna(0).astype(int)
    user_df = (
        summary_df
        .groupby("person", as_index=False)
        .agg(
            scan_count=("scan_count", "sum"),
            multiple_order_count=("multiple_order_count", "sum"),
            first_scan_at=("first_scan_at", "min"),
            last_scan_at=("last_scan_at", "max"),
        )
        .rename(columns={"person": "name"})
    )
    user_df["first_scan_at"] = pd.to_datetime(user_df["first_scan_at"], errors="coerce", utc=True)
    user_df["last_scan_at"] = pd.to_datetime(user_df["last_scan_at"], errors="coerce", utc=True)
    user_df["working_hours"] = (user_df["last_scan_at"] - user_df["first_scan_at"]).dt.total_seconds() / 3600
    return user_df.sort_values("scan_count", ascending=False).reset_index(drop=True)
