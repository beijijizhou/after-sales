from hashlib import sha1

import pandas as pd
import streamlit as st

from utils.sku_sorting import sort_sku_rows


SOURCE_LABELS = {
    "opening": "期初库存",
    "bulk": "正常入库",
    "transfer": "临时调货",
    "consumable_inbound": "耗材入库",
    "consumable_adjustment": "耗材库存修正",
}


def build_inbound_batch_summary(finance_df):
    columns = [
        "批次号", "批次名称", "首个 SKU", "记录时间", "入库日期", "来源", "部门",
        "品类", "SKU数", "数量", "生产库存数量", "耗材项数", "金额",
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
    inbound["batch_label"] = _batch_labels(inbound)
    inbound["first_sku"] = inbound.apply(_sku_label, axis=1)
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
    domains = inbound.get(
        "inventory_domain", pd.Series("生产库存", index=inbound.index)
    ).fillna("生产库存")
    inbound["production_quantity"] = inbound["quantity"].where(
        domains.ne("耗材库存"), 0
    )
    inbound["consumable_count"] = domains.eq("耗材库存").astype(int)
    inbound = sort_sku_rows(
        inbound,
        material="material",
        color="color",
        size="size",
        leading=["department", "category"],
    )
    result = (
        inbound.groupby("batch_key", as_index=False, dropna=False)
        .agg(
            recorded_at=("recorded_at", "max"),
            batch_label=("batch_label", "first"),
            first_sku=("first_sku", "first"),
            date=("date", "first"),
            source_type=("source_type", "first"),
            department=("department", _summarize_values),
            category=("category", _summarize_values),
            sku_count=("record_id", "count"),
            production_quantity=("production_quantity", "sum"),
            consumable_count=("consumable_count", "sum"),
            amount=("amount", "sum"),
        )
        .rename(columns={
            "batch_key": "批次号", "batch_label": "批次名称",
            "first_sku": "首个 SKU",
            "recorded_at": "记录时间",
            "date": "入库日期", "source_type": "来源",
            "department": "部门", "category": "品类",
            "sku_count": "SKU数", "production_quantity": "生产库存数量",
            "consumable_count": "耗材项数", "amount": "金额",
        })
    )
    result["来源"] = result["来源"].map(SOURCE_LABELS).fillna(result["来源"])
    result.loc[
        result["批次号"].astype(str).str.startswith("货柜:"), "来源"
    ] = "货柜入库"
    result["数量"] = result["生产库存数量"]
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
            f"{_format_recorded_at(row['记录时间'])}｜{row['部门']}｜"
            f"{row['首个 SKU']}｜"
            f"生产库存 {int(row['生产库存数量']):,} 件｜"
            f"耗材 {int(row['耗材项数'])} 项｜${row['金额']:,.2f}"
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
    metric_cols[1].metric(
        "生产库存 / 耗材",
        f"{int(selected_summary['生产库存数量']):,} 件 / "
        f"{int(selected_summary['耗材项数'])} 项",
    )
    metric_cols[2].metric("批次金额", f"${selected_summary['金额']:,.2f}")
    st.caption(
        f"{selected_summary['部门']}｜首个 SKU：{selected_summary['首个 SKU']}"
    )
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
    detail = rows.rename(columns={
        "date": "入库日期", "source_type": "来源",
        "department": "部门", "category": "品类", "brand": "品牌",
        "material": "材质", "color": "颜色", "size": "尺码/型号",
        "inventory_domain": "库存类型", "quantity": "数量",
        "quantity_unit": "单位", "unit_cost": "单位成本", "amount": "金额",
    })[[
        "入库日期", "库存类型", "来源", "部门", "品类", "品牌", "材质",
        "颜色", "尺码/型号", "数量", "单位", "单位成本", "金额",
    ]]
    return sort_sku_rows(detail)


def _summarize_values(values):
    unique = [
        value for value in dict.fromkeys(
            str(value or "").strip() for value in values
        ) if value
    ]
    return unique[0] if len(unique) == 1 else "多项"


def _batch_keys(rows):
    business = rows.get(
        "business_batch_key", pd.Series("", index=rows.index)
    ).fillna("").astype(str)
    keys = (
        rows["batch_id"].fillna("").astype(str)
        if "batch_id" in rows else pd.Series("", index=rows.index)
    )
    keys = business.where(business.str.strip() != "", keys)
    missing = keys.str.strip() == ""
    keys.loc[missing] = "成本批次-" + rows.loc[
        missing, "record_id"
    ].astype(str)
    return keys


def _batch_labels(rows):
    labels = rows.get(
        "business_batch_label", pd.Series("", index=rows.index)
    ).fillna("").astype(str)
    keys = _batch_keys(rows)
    return labels.where(labels.str.strip() != "", keys)


def _sku_label(row):
    values = [
        row.get("category"), row.get("brand"), row.get("material"),
        row.get("color"), row.get("size"),
    ]
    visible = [
        str(value).strip() for value in values
        if pd.notna(value) and str(value).strip()
    ]
    return "｜".join(dict.fromkeys(visible)) or "未命名 SKU"


def _format_recorded_at(value):
    timestamp = pd.to_datetime(value, errors="coerce")
    return timestamp.strftime("%Y-%m-%d %H:%M") if not pd.isna(timestamp) else "时间未知"
