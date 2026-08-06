from hashlib import sha1

import pandas as pd
import streamlit as st


SOURCE_LABELS = {
    "opening": "期初库存",
    "bulk": "正常入库",
    "transfer": "临时调货",
}


def build_inbound_batch_summary(finance_df):
    columns = [
        "批次号", "记录时间", "入库日期", "来源", "部门", "品类",
        "SKU数", "数量", "金额",
    ]
    if finance_df.empty:
        return pd.DataFrame(columns=columns)
    inbound = finance_df[
        (finance_df["direction"] == "入库")
        & finance_df["record_id"].notna()
    ].copy()
    if inbound.empty:
        return pd.DataFrame(columns=columns)
    inbound["batch_key"] = _batch_keys(inbound)
    missing_batch = inbound["batch_key"].str.strip() == ""
    inbound.loc[missing_batch, "batch_key"] = (
        "成本批次-" + inbound.loc[missing_batch, "record_id"].astype(str)
    )
    recorded_values = (
        inbound["recorded_at"]
        if "recorded_at" in inbound else inbound["date"]
    )
    inbound["recorded_at"] = pd.to_datetime(recorded_values, errors="coerce")
    inbound["amount"] = pd.to_numeric(
        inbound["amount"], errors="coerce"
    ).fillna(0)
    result = (
        inbound.groupby("batch_key", as_index=False, dropna=False)
        .agg(
            recorded_at=("recorded_at", "max"),
            date=("date", "first"),
            source_type=("source_type", "first"),
            department=("department", _summarize_values),
            category=("category", _summarize_values),
            sku_count=("record_id", "count"),
            quantity=("quantity", "sum"),
            amount=("amount", "sum"),
        )
        .rename(columns={
            "batch_key": "批次号", "recorded_at": "记录时间",
            "date": "入库日期", "source_type": "来源",
            "department": "部门", "category": "品类",
            "sku_count": "SKU数", "quantity": "数量", "amount": "金额",
        })
    )
    result["来源"] = result["来源"].map(SOURCE_LABELS).fillna(result["来源"])
    return result[columns].sort_values(
        ["记录时间", "入库日期"], ascending=[False, False], na_position="last"
    ).reset_index(drop=True)


def render_inbound_batch_browser(finance_df):
    st.subheader("入库成本批次")
    summary = build_inbound_batch_summary(finance_df)
    if summary.empty:
        st.info("当前筛选范围没有入库成本批次")
        return
    labels = {
        row["批次号"]: (
            f"{_format_recorded_at(row['记录时间'])}｜{row['部门']} {row['品类']}｜"
            f"{row['来源']}｜{int(row['数量']):,} 件｜${row['金额']:,.2f}"
        )
        for row in summary.to_dict("records")
    }
    options = summary["批次号"].tolist()
    option_signature = sha1(
        "|".join(str(value) for value in options).encode()
    ).hexdigest()[:10]
    key = f"finance_inbound_cost_batch_{option_signature}"
    if key in st.session_state and st.session_state[key] not in options:
        del st.session_state[key]
    selected = st.selectbox(
        "选择入库成本批次（最新在前）",
        options,
        format_func=lambda value: labels.get(value, value),
        key=key,
    )
    selected_summary = summary[summary["批次号"] == selected].iloc[0]
    metric_cols = st.columns(3)
    metric_cols[0].metric("批次 SKU", f"{int(selected_summary['SKU数']):,}")
    metric_cols[1].metric("批次数量", f"{int(selected_summary['数量']):,}")
    metric_cols[2].metric("批次金额", f"${selected_summary['金额']:,.2f}")
    st.caption(f"批次号：{selected}")
    detail = _batch_detail(finance_df, selected)
    st.dataframe(
        detail,
        hide_index=True,
        width="stretch",
        column_config={
            "数量": st.column_config.NumberColumn(format="%d"),
            "单位成本": st.column_config.NumberColumn(format="$%.4f"),
            "金额": st.column_config.NumberColumn(format="$%.2f"),
        },
    )


def _batch_detail(finance_df, batch_key):
    inbound = finance_df[finance_df["direction"] == "入库"].copy()
    keys = _batch_keys(inbound)
    rows = inbound[keys == batch_key].copy()
    rows["source_type"] = rows["source_type"].map(SOURCE_LABELS).fillna(
        rows["source_type"]
    )
    return rows.rename(columns={
        "date": "入库日期", "source_type": "来源",
        "department": "部门", "category": "品类", "brand": "品牌",
        "material": "材质", "color": "颜色", "size": "尺码/型号",
        "quantity": "数量", "unit_cost": "单位成本", "amount": "金额",
    })[[
        "入库日期", "来源", "部门", "品类", "品牌", "材质", "颜色",
        "尺码/型号", "数量", "单位成本", "金额",
    ]].sort_values(["材质", "颜色", "尺码/型号"]).reset_index(drop=True)


def _summarize_values(values):
    unique = [
        value for value in dict.fromkeys(
            str(value or "").strip() for value in values
        ) if value
    ]
    return unique[0] if len(unique) == 1 else "多项"


def _batch_keys(rows):
    keys = (
        rows["batch_id"].fillna("").astype(str)
        if "batch_id" in rows else pd.Series("", index=rows.index)
    )
    missing = keys.str.strip() == ""
    keys.loc[missing] = "成本批次-" + rows.loc[
        missing, "record_id"
    ].astype(str)
    return keys


def _format_recorded_at(value):
    timestamp = pd.to_datetime(value, errors="coerce")
    return timestamp.strftime("%Y-%m-%d %H:%M") if not pd.isna(timestamp) else "时间未知"
