import pandas as pd


SIZE_ORDER = ["S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]
SCOPE_VALID = "有效需求（排除已取消）"
SCOPE_PRODUCED = "仅已生产"
SCOPE_ALL = "全部记录"
SCOPE_OPTIONS = [SCOPE_VALID, SCOPE_PRODUCED, SCOPE_ALL]


def apply_production_scope(df, scope):
    if scope == SCOPE_PRODUCED:
        return df[df["生产项状态"].isin(["已生产", "已发货"])].copy()
    if scope == SCOPE_ALL:
        return df.copy()
    return df[df["生产项状态"] != "已取消"].copy()


def build_color_size_summary(df):
    row_columns = ["颜色"]
    if "品类" in df.columns:
        row_columns.insert(0, "品类")
    if df.empty:
        return pd.DataFrame(columns=[*row_columns, "合计"])
    source = df.copy()
    sizes = source["尺码"].fillna("").astype(str).str.strip()
    models = source.get("型号", "")
    if not isinstance(models, pd.Series):
        models = pd.Series(models, index=source.index)
    models = models.fillna("").astype(str).str.strip()
    source["规格"] = sizes.where(sizes != "", models)
    source.loc[source["规格"] == "", "规格"] = "未标注型号"
    model_columns = sorted(
        value for value in source.loc[sizes == "", "规格"].unique()
        if value
    )
    spec_columns = ([*SIZE_ORDER] if sizes.ne("").any() else [])
    spec_columns.extend(
        value for value in model_columns if value not in spec_columns
    )
    summary = source.pivot_table(
        index=row_columns,
        columns="规格",
        values="数量",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    for specification in spec_columns:
        if specification not in summary.columns:
            summary[specification] = 0
        summary[specification] = summary[specification].astype(int)
    summary["合计"] = summary[spec_columns].sum(axis=1)
    return summary[[*row_columns, *spec_columns, "合计"]].sort_values(
        "合计", ascending=False
    )


def build_material_summary(df):
    columns = ["材质"]
    if "品类" in df.columns:
        columns.insert(0, "品类")
    return _group_quantity(df, columns)


def build_platform_summary(df):
    columns = ["运营商", "品类"]
    if df.empty:
        return pd.DataFrame(
            columns=[*columns, "生产项数", "生产单数", "件数"]
        )
    return df.groupby(columns, as_index=False).agg(
        生产项数=("生产项编码", "nunique"),
        生产单数=("生产单号", "nunique"),
        件数=("数量", "sum"),
    ).sort_values("件数", ascending=False)


def build_status_summary(df):
    return _group_quantity(df, ["生产项状态"])


def build_daily_summary(df):
    if df.empty:
        return pd.DataFrame(columns=["创建日期", "生产项数", "生产单数", "件数"])
    source = df.dropna(subset=["创建时间"]).copy()
    source["创建日期"] = source["创建时间"].dt.date
    return source.groupby("创建日期", as_index=False).agg(
        生产项数=("生产项编码", "nunique"),
        生产单数=("生产单号", "nunique"),
        件数=("数量", "sum"),
    ).sort_values("创建日期", ascending=False)


def _group_quantity(df, columns):
    if df.empty:
        return pd.DataFrame(columns=[*columns, "生产项数", "件数"])
    return df.groupby(columns, as_index=False).agg(
        生产项数=("生产项编码", "nunique"),
        件数=("数量", "sum"),
    ).sort_values("件数", ascending=False)
