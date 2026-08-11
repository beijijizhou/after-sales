from hashlib import sha1

import pandas as pd
import streamlit as st

from db.finance import update_pending_cost_batch
from db.inventory.core.constants import SIZE_COLUMNS
from utils.sku_sorting import sort_sku_rows


IDENTITY_COLUMNS = [
    "business_date", "department", "category", "brand", "material",
    "color", "inventory_effect", "note",
]


def render_pending_cost_batches(supabase, rows):
    if rows.empty:
        return
    rows = _prepare(rows)
    summary = build_pending_cost_batch_summary(rows)
    st.markdown("#### 待复核成本批次")
    st.caption("同一批次按尺码横向展示；库存已包含的批次不会重复入库。")
    st.dataframe(summary.drop(columns=["批次键"]), width="stretch", hide_index=True)

    labels = {
        row["批次键"]: (
            f"{row['日期']}｜{row['品牌']} {row['材质']} {row['颜色']}｜"
            f"{int(row['总件数']):,} 件｜${float(row['总金额']):,.2f}"
        )
        for row in summary.to_dict("records")
    }
    selected = st.selectbox(
        "选择批次修改价格",
        summary["批次键"].tolist(),
        format_func=lambda key: labels.get(key, key),
        key="finance_pending_cost_batch",
    )
    batch_rows = sort_sku_rows(
        rows[rows["_batch_key"] == selected],
        material="material", color="color", size="size",
    )
    _render_batch_cost_editor(supabase, selected, batch_rows)


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


def _render_batch_cost_editor(supabase, batch_key, rows):
    active = rows[rows["size"].fillna("").str.upper().isin(SIZE_COLUMNS)]
    if active.empty:
        st.info("这个批次没有可修改的尺码明细")
        return
    key_suffix = sha1(batch_key.encode()).hexdigest()[:10]
    with st.form(f"pending_cost_{key_suffix}"):
        columns = st.columns(len(active))
        entered = []
        for column, (_, row) in zip(columns, active.iterrows()):
            size = str(row["size"]).upper()
            column.markdown(f"**{size}**")
            column.caption(f"{int(row['quantity']):,} 件")
            value = column.number_input(
                "单位成本",
                min_value=0.0,
                value=float(row["unit_cost"]) if pd.notna(row["unit_cost"]) else 0.0,
                step=0.0001,
                format="%.4f",
                key=f"pending_price_{key_suffix}_{size}",
            )
            entered.append((str(row["id"]), value))
        saved = st.form_submit_button("保存整批价格", width="stretch")
    if not saved:
        return
    for record_id, value in entered:
        update_pending_cost_batch(supabase, record_id, value)
    st.success(f"已保存这个批次 {len(entered)} 个尺码的成本，未改变库存数量")
    st.rerun()


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
    return "价格待复核"
