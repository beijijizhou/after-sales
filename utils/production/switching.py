import pandas as pd

from utils.production.constants import HALOO_PLATFORM, NY_TIMEZONE, OTHER_CLIENT


def build_person_switch_table(df):
    required_columns = {"hour_start_at", "person", "haloo_count", "other_count", "total_count"}
    if df.empty or not required_columns.issubset(df.columns):
        return pd.DataFrame()

    switch_df = prepare_switch_df(df)
    if switch_df.empty:
        return pd.DataFrame()

    switch_rows = [
        build_person_switch_row(person, person_df)
        for person, person_df in switch_df.sort_values("hour").groupby("person", sort=False)
    ]
    result_df = pd.DataFrame(switch_rows)
    return (
        result_df
        .sort_values(["切换次数", "_sort_count"], ascending=[False, False])
        .drop(columns=["_sort_count"])
        .reset_index(drop=True)
    )


def prepare_switch_df(df):
    switch_df = df.copy()
    switch_df["hour"] = pd.to_datetime(switch_df["hour_start_at"], errors="coerce", utc=True).dt.tz_convert(NY_TIMEZONE)
    switch_df = switch_df.dropna(subset=["hour"])
    switch_df["Haloo"] = pd.to_numeric(switch_df["haloo_count"], errors="coerce").fillna(0).astype(int)
    switch_df["小平台"] = pd.to_numeric(switch_df["other_count"], errors="coerce").fillna(0).astype(int)
    switch_df["总产量"] = pd.to_numeric(switch_df["total_count"], errors="coerce").fillna(0).astype(int)
    switch_df = switch_df[switch_df["总产量"] > 0]
    if switch_df.empty:
        return pd.DataFrame()

    switch_df["主要工作"] = switch_df.apply(
        lambda row: HALOO_PLATFORM if row["Haloo"] >= row["小平台"] else OTHER_CLIENT,
        axis=1,
    )
    return switch_df


def build_person_switch_row(person, person_df):
    compressed_path = compress_work_path(person_df["主要工作"].tolist())
    period_detail = " -> ".join(
        f"{row['work']}（{row['count']}）"
        for row in build_period_rows(person_df)
    )
    switch_count = max(len(compressed_path) - 1, 0)
    haloo_count = int(person_df["Haloo"].sum())
    other_count = int(person_df["小平台"].sum())
    return {
        "人员": person,
        "切换次数": switch_count,
        "切换路径": period_detail,
        "风险": get_switch_risk(switch_count),
        "_sort_count": haloo_count + other_count,
    }


def compress_work_path(work_path):
    compressed_path = []
    for work in work_path:
        if not compressed_path or compressed_path[-1] != work:
            compressed_path.append(work)
    return compressed_path


def build_period_rows(person_df):
    period_rows = []
    current_work = None
    period_count = 0

    for _, row in person_df.sort_values("hour").iterrows():
        row_work = row["主要工作"]
        if current_work is None:
            current_work = row_work
        elif row_work != current_work:
            period_rows.append({"work": current_work, "count": period_count})
            current_work = row_work
            period_count = 0

        period_count += int(row["Haloo"] if row_work == HALOO_PLATFORM else row["小平台"])

    if current_work is not None:
        period_rows.append({"work": current_work, "count": period_count})
    return period_rows


def get_switch_risk(switch_count):
    if switch_count <= 2:
        return "正常"
    if switch_count <= 4:
        return "注意"
    return "频繁切换"
