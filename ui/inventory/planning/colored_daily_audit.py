from datetime import timedelta

import pandas as pd
import streamlit as st

from automation.sync.colored_models import load_colored_ledger_history
from db.inventory.core.constants import SIZE_COLUMNS
from db.production_consumption import load_daily_platform_consumption


def render_colored_daily_erp_audit(supabase, current_date, days=30):
    end_date = current_date - timedelta(days=1)
    start_date = end_date - timedelta(days=int(days) - 1)
    st.subheader("彩色短袖每日 ERP 数据核对")
    st.caption(
        "直接读取数据库生产日表；每行均来自ERP/API同步后的标准化数据。"
        "库存已扣数量只作对照，差异不会反向修改ERP生产件数。"
    )
    try:
        production = load_daily_platform_consumption(
            supabase, "DTF", "彩色短袖", start_date, end_date
        )
        ledger = load_colored_ledger_history(
            supabase, start_date, end_date
        )
    except Exception as error:
        st.error(f"每日ERP数据加载失败：{error}")
        return
    summary = build_colored_daily_erp_summary(
        production, ledger, start_date, end_date
    )
    _render_daily_metrics(summary, days)
    st.dataframe(
        summary,
        hide_index=True,
        width="stretch",
        height=min(38 * (len(summary) + 1), 900),
        column_config={
            "日期": st.column_config.DateColumn(format="MM/DD/YYYY"),
            "ERP生产件数": st.column_config.NumberColumn(format="%d"),
            "库存已扣件数": st.column_config.NumberColumn(format="%d"),
            "待核对差异": st.column_config.NumberColumn(format="%d"),
            "生产记录数": st.column_config.NumberColumn(format="%d"),
        },
    )
    available_dates = summary.loc[
        summary["ERP生产件数"].gt(0), "日期"
    ].tolist()
    if not available_dates:
        st.warning(
            "最近30天数据库生产日表没有彩色短袖数据。当前消耗模型不能用"
            "库存扣减流水代替；请先修复ERP同步保存链路。"
        )
        return
    selected_date = st.selectbox(
        "查看某一天的ERP平台、颜色和尺码明细",
        available_dates,
        format_func=lambda value: value.strftime("%m/%d/%Y"),
        key="colored_daily_erp_audit_date",
    )
    detail = build_colored_daily_erp_detail(production, selected_date)
    st.dataframe(
        detail,
        hide_index=True,
        width="stretch",
        height=min(38 * (len(detail) + 1), 800),
    )


def build_colored_daily_erp_summary(
    production, ledger, start_date, end_date,
):
    dates = pd.DataFrame({
        "日期": pd.date_range(start_date, end_date, freq="D").date
    })
    source = pd.DataFrame(production).copy()
    if source.empty:
        daily = pd.DataFrame(columns=[
            "日期", "ERP生产件数", "生产记录数", "平台数", "已读取平台",
        ])
    else:
        source["日期"] = pd.to_datetime(
            source["business_date"], errors="coerce"
        ).dt.date
        source["quantity"] = pd.to_numeric(
            source["quantity"], errors="coerce"
        ).fillna(0)
        source["record_count"] = pd.to_numeric(
            source["record_count"], errors="coerce"
        ).fillna(0)
        daily = source.groupby("日期", as_index=False).agg(
            ERP生产件数=("quantity", "sum"),
            生产记录数=("record_count", "sum"),
            平台数=("platform", "nunique"),
            已读取平台=("platform", _joined_values),
        )
    deductions = pd.DataFrame(ledger).copy()
    if deductions.empty:
        issued = pd.DataFrame(columns=["日期", "库存已扣件数"])
    else:
        issued = deductions.groupby("日期", as_index=False).agg(
            库存已扣件数=("生产数量", "sum")
        )
    result = dates.merge(daily, on="日期", how="left").merge(
        issued, on="日期", how="left"
    )
    numeric = [
        "ERP生产件数", "生产记录数", "平台数", "库存已扣件数",
    ]
    for column in numeric:
        result[column] = pd.to_numeric(
            result[column], errors="coerce"
        ).fillna(0).astype(int)
    result["已读取平台"] = result["已读取平台"].fillna("—")
    result["待核对差异"] = (
        result["ERP生产件数"] - result["库存已扣件数"]
    )
    result["状态"] = result.apply(_daily_status, axis=1)
    return result[[
        "日期", "状态", "ERP生产件数", "库存已扣件数", "待核对差异",
        "平台数", "已读取平台", "生产记录数",
    ]].sort_values("日期", ascending=False).reset_index(drop=True)


def build_colored_daily_erp_detail(production, selected_date):
    source = pd.DataFrame(production).copy()
    columns = ["平台", "颜色", *SIZE_COLUMNS, "其他尺码", "合计", "记录数"]
    if source.empty:
        return pd.DataFrame(columns=columns)
    source["日期"] = pd.to_datetime(
        source["business_date"], errors="coerce"
    ).dt.date
    source = source[source["日期"].eq(selected_date)].copy()
    if source.empty:
        return pd.DataFrame(columns=columns)
    source["尺码列"] = source["size"].where(
        source["size"].isin(SIZE_COLUMNS), "其他尺码"
    )
    source["quantity"] = pd.to_numeric(
        source["quantity"], errors="coerce"
    ).fillna(0)
    wide = source.pivot_table(
        index=["platform", "color"], columns="尺码列",
        values="quantity", aggfunc="sum", fill_value=0,
    ).reindex(columns=[*SIZE_COLUMNS, "其他尺码"], fill_value=0)
    totals = source.groupby(["platform", "color"]).agg(
        合计=("quantity", "sum"), 记录数=("record_count", "sum")
    )
    result = wide.join(totals).reset_index().rename(columns={
        "platform": "平台", "color": "颜色",
    })
    for column in [*SIZE_COLUMNS, "其他尺码", "合计", "记录数"]:
        result[column] = pd.to_numeric(
            result[column], errors="coerce"
        ).fillna(0).astype(int)
    return result[columns].sort_values(
        ["平台", "颜色"]
    ).reset_index(drop=True)


def _render_daily_metrics(summary, days):
    total = int(summary["ERP生产件数"].sum())
    covered = int(summary["ERP生产件数"].gt(0).sum())
    missing = int(days) - covered
    columns = st.columns(4)
    columns[0].metric("30天ERP生产", f"{total:,} 件")
    columns[1].metric("自然日均", f"{total / max(int(days), 1):,.1f} 件")
    columns[2].metric("有ERP数据", f"{covered}/{int(days)} 天")
    columns[3].metric("无ERP日表", f"{missing} 天")


def _joined_values(values):
    return "、".join(sorted({
        str(value).strip() for value in values if str(value).strip()
    })) or "—"


def _daily_status(row):
    if int(row["ERP生产件数"]) > 0:
        return "已保存"
    if int(row["库存已扣件数"]) > 0:
        return "缺少ERP日表"
    return "无已保存数据"
