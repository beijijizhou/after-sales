import pandas as pd
import streamlit as st

from db.inventory.core.constants import SIZE_COLUMNS
from hashlib import sha1


IDENTITY_COLUMNS = [
    "business_date", "department", "category", "brand", "material",
    "color", "inventory_effect", "note",
]


def render_pending_cost_batches(rows):
    if rows.empty:
        return
    rows = _prepare(rows)
    summary = build_pending_cost_batch_summary(rows)
    st.markdown("#### 待到货与待处理成本批次")
    st.caption(
        "财务页面仅展示；修改件数、尺码或价格请到“库存 → 临时库存调整”。"
    )
    st.dataframe(summary.drop(columns=["批次键"]), width="stretch", hide_index=True)


def build_pending_cost_batch_summary(rows):
    columns = [
        "批次键", "日期", "部门", "品类", "品牌", "材质", "颜色",
        *SIZE_COLUMNS, "总件数", "总金额", "状态",
    ]
    if rows.empty:
        return pd.DataFrame(columns=columns)
    data = _prepare(rows)
    records = []
    for batch_key, batch in data.groupby("_batch_key", sort=False):
        first = batch.iloc[0]
        record = {
            "批次键": batch_key,
            "日期": first["business_date"],
            "部门": first["department"],
            "品类": first["category"],
            "品牌": first["brand"],
            "材质": first["material"],
            "颜色": first["color"],
            "总件数": int(batch["quantity"].sum()),
            "总金额": float((batch["quantity"] * batch["unit_cost"].fillna(0)).sum()),
            "状态": _status_label(batch),
        }
        for size in SIZE_COLUMNS:
            sized = batch[batch["size"].fillna("").str.upper() == size]
            record[size] = "" if sized.empty else _size_cell(sized)
        records.append(record)
    return pd.DataFrame(records, columns=columns).sort_values(
        "日期", ascending=False
    ).reset_index(drop=True)


def _prepare(rows):
    data = rows.copy()
    data["quantity"] = pd.to_numeric(data["quantity"], errors="coerce").fillna(0)
    data["unit_cost"] = pd.to_numeric(data["unit_cost"], errors="coerce")
    identity = data[IDENTITY_COLUMNS].fillna("").astype(str).agg("||".join, axis=1)
    data["_batch_key"] = identity.map(lambda value: sha1(value.encode()).hexdigest()[:16])
    return data


def _size_cell(rows):
    quantity = int(rows["quantity"].sum())
    costs = rows["unit_cost"].dropna().unique().tolist()
    if len(costs) == 1:
        return f"{quantity:,} × ${float(costs[0]):.4f}"
    return f"{quantity:,}｜价格待核对"


def _status_label(rows):
    if rows["unit_cost"].isna().any():
        return "待核价"
    if (rows["inventory_effect"] == "not_posted").all():
        return "待到货"
    return "价格已录入"
