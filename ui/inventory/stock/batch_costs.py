"""Batch-first inventory cost maintenance workflows."""

from hashlib import sha1
import re

import pandas as pd
import streamlit as st

from db.batches import (
    InboundBatchKind,
    InboundBatchReference,
    InboundCostCorrection,
    replace_inbound_batch,
)
from db.inventory import SIZE_COLUMNS
from db.inventory.core.costs import (
    fill_missing_inventory_group_costs,
    fill_missing_inventory_sku_costs,
)
from utils.auth import get_current_operator_name
from utils.sku_sorting import sort_sku_rows
from ui.table_layout import fit_table_height


SOURCE_LABELS = {
    "opening": "初始化库存",
    "bulk": "正常入库",
    "transfer": "临时调货",
    "consumable_inbound": "耗材入库",
    "consumable_adjustment": "耗材库存修正",
}
TARGET_IDENTITY = ["department", "category", "brand", "material", "color"]


def render_reference_cost_fill(
    supabase, finance_df, history_cache_key=None,
):
    missing_groups = build_missing_cost_groups(finance_df)
    if missing_groups.empty:
        return
    categories = set(missing_groups["品类"].fillna("").astype(str))
    if categories == {"彩色短袖"}:
        render_colored_previous_brand_cost_fill(
            supabase, finance_df, history_cache_key=history_cache_key
        )
        st.divider()
    st.subheader("按参考价格批量补成本")
    st.caption(
        "选择缺成本的 SKU 组合并指定参考材质；系统只补空白或 0 成本，"
        "不会覆盖已经填写的历史价格。确认前按原入库批次显示完整预览。"
    )
    options = missing_groups["目标键"].tolist()
    labels = {
        row["目标键"]: (
            f"{row['部门']}｜{row['品类']}｜{row['品牌']}｜"
            f"{row['材质']}｜{row['颜色']}｜"
            f"{int(row['缺成本批次']):,} 批｜{int(row['缺成本数量']):,} 件"
        )
        for row in missing_groups.to_dict("records")
    }
    pasted = st.text_area(
        "批量粘贴品牌 / 材质 / 颜色",
        placeholder="Haloo  180g  白\n杂牌  160g  白",
        help="每行一组；可用空格、Tab、/ 或｜分隔。",
        key="finance_reference_cost_pasted_targets",
    )
    pasted_selected, unmatched = resolve_pasted_cost_targets(
        pasted, missing_groups
    )
    manually_selected = st.multiselect(
        "需要补成本的 SKU 范围", options,
        format_func=lambda value: labels.get(value, value),
        key="finance_reference_cost_targets",
    )
    selected = list(dict.fromkeys([*pasted_selected, *manually_selected]))
    if unmatched:
        st.warning("未匹配以下范围：" + "；".join(unmatched))
    selected_groups = missing_groups[
        missing_groups["目标键"].isin(selected)
    ]
    reference_scope = _common_reference_scope(selected_groups)
    reference_materials = priced_reference_materials(
        finance_df, **reference_scope
    )
    if not reference_materials:
        st.warning("当前没有可作为参考的已填写材质价格。")
        return
    default_index = (
        reference_materials.index("CVC")
        if "CVC" in reference_materials else 0
    )
    reference_material = st.selectbox(
        "参考材质", reference_materials, index=default_index,
        key="finance_reference_cost_material",
    )
    suggested = latest_material_cost(
        finance_df, reference_material, **reference_scope
    )
    unit_cost = st.number_input(
        "本次采用单位成本", min_value=0.0001, step=0.0001,
        value=float(suggested), format="%.4f",
        key=f"finance_reference_cost_value_{reference_material}",
    )
    reference = latest_material_cost_source(
        finance_df, reference_material, **reference_scope
    )
    if reference:
        st.caption(
            f"参考来源：{reference['日期']}｜{reference['品牌']} "
            f"{reference['材质']} {reference['颜色']}｜"
            f"最近有效入库价 ${reference['单位成本']:.4f}"
        )
    if not selected:
        st.info("请选择需要补成本的 SKU 范围，系统才会生成批次预览。")
        return
    preview, lots = build_reference_cost_preview(
        finance_df, selected, unit_cost
    )
    if lots.empty:
        st.info("所选范围目前没有缺成本批次。")
        return
    metrics = st.columns(3)
    metrics[0].metric("涉及批次", f"{lots['_batch_key'].nunique():,}")
    metrics[1].metric("补价记录", f"{len(lots):,}")
    metrics[2].metric(
        "补价金额", f"${float(lots['quantity'].sum()) * unit_cost:,.2f}"
    )
    st.markdown("#### 按批次补价预览")
    st.dataframe(
        preview, hide_index=True, width="stretch",
        height=fit_table_height(preview),
        column_config={
            **{
                size: st.column_config.NumberColumn(size, format="%d")
                for size in SIZE_COLUMNS
            },
            "总件数": st.column_config.NumberColumn(format="%d"),
            "采用单价": st.column_config.NumberColumn(format="$%.4f"),
            "补价金额": st.column_config.NumberColumn(format="$%.2f"),
        },
    )
    confirmed = st.checkbox(
        "我已核对批次、SKU 范围和参考单价",
        key="finance_reference_cost_confirm",
    )
    if not st.button(
        "确认按预览批量补成本", type="primary", width="stretch",
        disabled=not confirmed, key="finance_reference_cost_save",
    ):
        return
    progress = st.progress(0, text="正在保存批次成本...")
    saved = 0
    try:
        total = len(lots)
        for index, row in enumerate(lots.to_dict("records"), start=1):
            kind = (
                InboundBatchKind.CONSUMABLE_MOVEMENT
                if str(row.get("source_type") or "").startswith("consumable_")
                else InboundBatchKind.INVENTORY_COST_LOT
            )
            replace_inbound_batch(
                supabase,
                InboundBatchReference(kind, row["record_id"]),
                InboundCostCorrection(unit_cost),
                get_current_operator_name(),
            )
            saved = index
            progress.progress(
                index / total, text=f"正在保存批次成本：{index}/{total}"
            )
        inventory_updated = fill_missing_inventory_group_costs(
            supabase,
            selected_groups.rename(columns={
                "部门": "department", "品类": "category",
                "品牌": "brand", "材质": "material", "颜色": "color",
            }),
            unit_cost,
        )
    except Exception as error:
        st.error(
            f"批量补成本在第 {saved + 1} 条停止；已完成 {saved} 条。"
            f"请重新读取后继续，错误：{error}"
        )
        return
    st.session_state["finance_cost_saved"] = (
        f"已按 {reference_material} 参考价 ${unit_cost:.4f} "
        f"补充 {saved} 条批次成本，并同步 {inventory_updated} 个当前库存 SKU"
    )
    if history_cache_key:
        st.session_state.pop(history_cache_key, None)
    st.rerun()


def render_colored_previous_brand_cost_fill(
    supabase, finance_df, history_cache_key=None,
):
    matches = match_previous_brand_costs(finance_df)
    st.subheader("按同品牌上次成本补齐")
    st.caption(
        "彩色短袖按品牌、材质和尺码继承该批次之前最近一次有效成本；"
        "颜色不影响价格。Haloo 只使用 Haloo 历史价，临时进货只使用"
        "该临时进货品牌历史价。早期批次若发生在首笔有效价格之前，"
        "使用随后最早一笔同品牌价格并明确标记为回溯参考。"
    )
    if matches.empty:
        st.info("当前缺成本批次没有可核对的同品牌历史价格。")
        return
    preview = build_previous_brand_cost_preview(matches)
    st.dataframe(
        preview, hide_index=True, width="stretch",
        height=fit_table_height(preview),
    )
    metrics = st.columns(3)
    metrics[0].metric("可补批次", f"{matches['_batch_key'].nunique():,}")
    metrics[1].metric("可补记录", f"{len(matches):,}")
    metrics[2].metric(
        "补价金额",
        f"${float((matches['quantity'] * matches['reference_cost']).sum()):,.2f}",
    )
    confirmed = st.checkbox(
        "我已核对同品牌历史价格与批次明细",
        key="colored_previous_brand_cost_confirm",
    )
    if not st.button(
        "确认按同品牌上次成本补齐", type="primary", width="stretch",
        disabled=not confirmed, key="colored_previous_brand_cost_save",
    ):
        return
    progress = st.progress(0, text="正在按同品牌历史价格补成本…")
    for index, row in enumerate(matches.to_dict("records"), start=1):
        replace_inbound_batch(
            supabase,
            InboundBatchReference(
                InboundBatchKind.INVENTORY_COST_LOT, row["record_id"]
            ),
            InboundCostCorrection(row["reference_cost"]),
            get_current_operator_name(),
        )
        progress.progress(index / len(matches))
    inventory_rows = matches.rename(columns={
        "reference_cost": "unit_cost",
    })
    inventory_updated = fill_missing_inventory_sku_costs(
        supabase, inventory_rows
    )
    st.session_state["finance_cost_saved"] = (
        f"已按同品牌上次成本补充 {len(matches)} 条批次记录，"
        f"并同步 {inventory_updated} 个当前库存 SKU"
    )
    if history_cache_key:
        st.session_state.pop(history_cache_key, None)
    st.rerun()


def build_missing_cost_groups(finance_df):
    data = _prepare_inbound(finance_df)
    columns = [
        "目标键", "部门", "品类", "品牌", "材质", "颜色",
        "缺成本批次", "缺成本记录", "缺成本数量",
    ]
    if data.empty:
        return pd.DataFrame(columns=columns)
    costs = pd.to_numeric(data["unit_cost"], errors="coerce")
    data = data[costs.isna() | costs.le(0)].copy()
    if data.empty:
        return pd.DataFrame(columns=columns)
    data["目标键"] = _target_keys(data)
    result = data.groupby(
        ["目标键", *TARGET_IDENTITY], as_index=False, dropna=False
    ).agg(
        missing_batches=("_batch_key", "nunique"),
        missing_records=("record_id", "count"),
        missing_quantity=("quantity", "sum"),
    ).rename(columns={
        "department": "部门", "category": "品类", "brand": "品牌",
        "material": "材质", "color": "颜色",
        "missing_batches": "缺成本批次",
        "missing_records": "缺成本记录", "missing_quantity": "缺成本数量",
    })
    return result[columns].sort_values(
        ["部门", "品类", "材质", "品牌", "颜色"], kind="stable"
    ).reset_index(drop=True)


def build_missing_cost_batch_overview(finance_df):
    """Show every missing-cost SKU grouped by its human business batch."""
    data = _prepare_inbound(pd.DataFrame(finance_df).copy())
    columns = [
        "日期", "批次", "来源", "品类", "缺成本 SKU",
        "缺成本 SKU 数", "批次数量",
    ]
    if data.empty:
        return pd.DataFrame(columns=columns)
    costs = pd.to_numeric(data["unit_cost"], errors="coerce")
    data = data[costs.isna() | costs.le(0)].copy()
    if data.empty:
        return pd.DataFrame(columns=columns)

    labels = data.get(
        "business_batch_label", pd.Series("", index=data.index)
    ).fillna("").astype(str).str.strip()
    dates = pd.to_datetime(data["date"], errors="coerce").dt.strftime("%m/%d")
    sources = data["source_type"].map(SOURCE_LABELS).fillna(
        data["source_type"]
    ).fillna("入库")
    data["批次"] = labels.where(
        labels.ne(""), dates.fillna("—") + " " + sources.astype(str)
    )
    data["日期"] = pd.to_datetime(data["date"], errors="coerce").dt.date
    data["来源"] = sources
    data["品类"] = data["category"].map(_display_value)
    data["缺成本 SKU"] = data.apply(_missing_cost_sku_label, axis=1)

    result = data.groupby(
        ["_batch_key", "日期", "批次", "来源", "品类"],
        as_index=False, dropna=False,
    ).agg(
        missing_skus=("缺成本 SKU", lambda values: "；".join(dict.fromkeys(values))),
        missing_count=("record_id", "count"),
        quantity=("quantity", "sum"),
    ).rename(columns={
        "missing_skus": "缺成本 SKU",
        "missing_count": "缺成本 SKU 数",
        "quantity": "批次数量",
    })
    result["缺成本 SKU 数"] = pd.to_numeric(
        result["缺成本 SKU 数"], errors="coerce"
    ).fillna(0).astype(int)
    result["批次数量"] = pd.to_numeric(
        result["批次数量"], errors="coerce"
    ).fillna(0).astype(int)
    return result.sort_values(
        "日期", ascending=False, na_position="last", kind="stable"
    )[columns].reset_index(drop=True)


def _missing_cost_sku_label(row):
    values = [
        row.get("brand"), row.get("material"), row.get("color"), row.get("size")
    ]
    visible = [
        str(value).strip() for value in values
        if pd.notna(value) and str(value).strip()
    ]
    return "｜".join(visible) if visible else "未命名 SKU"


def match_previous_brand_costs(finance_df):
    """Match colored-shirt missing lots to the prior same-brand SKU cost."""
    data = _prepare_inbound(finance_df)
    if data.empty:
        return data
    data = data[data["category"].fillna("").astype(str).eq("彩色短袖")].copy()
    if data.empty:
        return data
    data["_cost"] = pd.to_numeric(data["unit_cost"], errors="coerce")
    data["_date"] = pd.to_datetime(data["date"], errors="coerce")
    data["_recorded"] = pd.to_datetime(
        data.get("recorded_at", pd.Series(pd.NaT, index=data.index)),
        errors="coerce", utc=True,
    )
    key_columns = [
        "department", "category", "brand", "material", "size",
    ]
    priced = data[data["_cost"].gt(0)].copy()
    missing = data[data["_cost"].isna() | data["_cost"].le(0)].copy()
    matched = []
    for row in missing.to_dict("records"):
        candidates = priced.copy()
        for column in key_columns:
            candidates = candidates[
                candidates[column].fillna("").astype(str).eq(
                    str(row.get(column) or "")
                )
            ]
        if candidates.empty:
            continue
        ordered = candidates.sort_values(
            ["_date", "_recorded"], na_position="first"
        )
        row_date = row.get("_date")
        prior = ordered
        if not pd.isna(row_date):
            prior = ordered[
                ordered["_date"].isna() | ordered["_date"].le(row_date)
            ]
        if prior.empty:
            reference = ordered.iloc[0]
            row["reference_mode"] = "回溯参考"
        else:
            reference = prior.iloc[-1]
            row["reference_mode"] = "历史价格"
        row["reference_cost"] = float(reference["_cost"])
        row["reference_date"] = reference["_date"]
        row["reference_color"] = reference.get("color")
        matched.append(row)
    return pd.DataFrame(matched)


def build_previous_brand_cost_preview(matches):
    data = pd.DataFrame(matches).copy()
    if data.empty:
        return data
    data["日期"] = pd.to_datetime(data["date"], errors="coerce").dt.date
    data["参考日期"] = pd.to_datetime(
        data["reference_date"], errors="coerce"
    ).dt.date
    labels = data.get(
        "business_batch_label", pd.Series("", index=data.index)
    ).fillna("").astype(str)
    batch_ids = data.get(
        "batch_id", pd.Series("", index=data.index)
    ).fillna("").astype(str)
    data["批次"] = labels.where(labels.str.strip() != "", batch_ids)
    data["批次"] = data["批次"].where(
        data["批次"].str.strip() != "", "旧版初始化批次"
    )
    data["价格明细"] = data.apply(
        lambda row: (
            f"{int(row['quantity']):,} × ${float(row['reference_cost']):.4f}"
        ),
        axis=1,
    )
    preview = data.pivot_table(
        index=[
            "日期", "批次", "brand", "material", "color", "参考日期",
            "reference_mode",
        ],
        columns="size", values="价格明细", aggfunc="first", fill_value="",
    ).reset_index().rename(columns={
        "brand": "品牌", "material": "材质", "color": "颜色",
        "reference_mode": "参考方式",
    })
    for size in SIZE_COLUMNS:
        if size not in preview:
            preview[size] = ""
    total_keys = [
        "日期", "批次", "brand", "material", "color", "参考日期",
        "reference_mode",
    ]
    totals = data.groupby(
        total_keys, as_index=False, dropna=False
    )["quantity"].sum().rename(columns={
        "brand": "品牌", "material": "材质", "color": "颜色",
        "reference_mode": "参考方式",
        "quantity": "总件数",
    })
    preview = preview.merge(
        totals,
        on=[
            "日期", "批次", "品牌", "材质", "颜色", "参考日期", "参考方式",
        ],
        how="left",
    )
    preview = sort_sku_rows(
        preview, material="材质", color="颜色",
        leading=["日期", "批次"], leading_ascending=[False, True],
    )
    return preview[[
        "日期", "批次", "品牌", "材质", "颜色", *SIZE_COLUMNS,
        "总件数", "参考日期", "参考方式",
    ]].reset_index(drop=True)


def filter_cost_history_scope(rows, department, category=""):
    data = pd.DataFrame(rows).copy()
    if data.empty:
        return data
    expected_department = str(department or "").strip().casefold()
    if expected_department:
        values = (
            data["department"].fillna("").astype(str).str.strip().str.casefold()
        )
        data = data[values.eq(expected_department)]
    expected_category = str(category or "").strip().casefold()
    if expected_category:
        values = (
            data["category"].fillna("").astype(str).str.strip().str.casefold()
        )
        data = data[values.eq(expected_category)]
    return data.reset_index(drop=True)


def resolve_pasted_cost_targets(pasted, missing_groups):
    if not str(pasted or "").strip() or missing_groups.empty:
        return [], []
    lookup = {}
    for row in missing_groups.to_dict("records"):
        identity = tuple(
            str(row[column] or "").strip().casefold()
            for column in ["品牌", "材质", "颜色"]
        )
        lookup.setdefault(identity, []).append(row["目标键"])
    selected = []
    unmatched = []
    for raw_line in str(pasted).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        normalized = re.sub(r"[｜|/，,]+", "\t", line)
        if "\t" in normalized:
            fields = [value.strip() for value in normalized.split("\t") if value.strip()]
        else:
            fields = normalized.rsplit(maxsplit=2)
        if len(fields) < 3:
            unmatched.append(line)
            continue
        identity = tuple(value.casefold() for value in fields[-3:])
        matches = lookup.get(identity, [])
        if not matches:
            unmatched.append(line)
            continue
        selected.extend(matches)
    return list(dict.fromkeys(selected)), unmatched


def priced_reference_materials(
    finance_df, *, department=None, category=None,
):
    data = _filter_reference_scope(
        _prepare_inbound(finance_df), department, category
    )
    if data.empty:
        return []
    costs = pd.to_numeric(data["unit_cost"], errors="coerce")
    values = data.loc[costs.gt(0), "material"].fillna("").astype(str)
    return list(dict.fromkeys(value for value in values if value))


def latest_material_cost(
    finance_df, material, *, department=None, category=None,
):
    source = latest_material_cost_source(
        finance_df, material, department=department, category=category
    )
    return float(source["单位成本"]) if source else 0.0001


def latest_material_cost_source(
    finance_df, material, *, department=None, category=None,
):
    data = _filter_reference_scope(
        _prepare_inbound(finance_df), department, category
    )
    if data.empty:
        return None
    data["_cost"] = pd.to_numeric(data["unit_cost"], errors="coerce")
    data["_date"] = pd.to_datetime(data["date"], errors="coerce")
    recorded = data.get(
        "recorded_at", pd.Series(pd.NaT, index=data.index)
    )
    data["_recorded"] = pd.to_datetime(recorded, errors="coerce", utc=True)
    matches = data[
        data["material"].fillna("").astype(str).eq(str(material))
        & data["_cost"].gt(0)
    ].sort_values(["_date", "_recorded"], na_position="first")
    if matches.empty:
        return None
    row = matches.iloc[-1]
    return {
        "日期": row["_date"].date() if not pd.isna(row["_date"]) else "—",
        "品牌": _display_value(row.get("brand")),
        "材质": _display_value(row.get("material")),
        "颜色": _display_value(row.get("color")),
        "单位成本": float(row["_cost"]),
    }


def build_reference_cost_preview(finance_df, target_keys, unit_cost):
    data = _prepare_inbound(finance_df)
    if data.empty:
        return pd.DataFrame(), data
    costs = pd.to_numeric(data["unit_cost"], errors="coerce")
    data["目标键"] = _target_keys(data)
    lots = data[
        data["目标键"].isin(set(target_keys))
        & (costs.isna() | costs.le(0))
    ].copy()
    if lots.empty:
        return pd.DataFrame(), lots
    labels = lots.get(
        "business_batch_label", pd.Series("", index=lots.index)
    ).fillna("").astype(str)
    batch_ids = lots.get(
        "batch_id", pd.Series("", index=lots.index)
    ).fillna("").astype(str)
    lots["批次"] = labels.where(labels.str.strip() != "", batch_ids)
    lots["批次"] = lots["批次"].where(
        lots["批次"].str.strip() != "", "旧版初始化批次"
    )
    lots["日期"] = pd.to_datetime(lots["date"], errors="coerce").dt.date
    lots["来源"] = lots["source_type"].map(SOURCE_LABELS).fillna(
        lots["source_type"]
    )
    grouped = lots.groupby(
        ["日期", "批次", "来源", "brand", "material", "color", "size"],
        as_index=False, dropna=False,
    ).agg(数量=("quantity", "sum"))
    preview = grouped.pivot_table(
        index=["日期", "批次", "来源", "brand", "material", "color"],
        columns="size", values="数量", aggfunc="sum", fill_value=0,
    ).reset_index().rename(columns={
        "brand": "品牌", "material": "材质", "color": "颜色",
    })
    for size in SIZE_COLUMNS:
        if size not in preview:
            preview[size] = 0
        preview[size] = pd.to_numeric(
            preview[size], errors="coerce"
        ).fillna(0).astype(int)
    preview["总件数"] = preview[SIZE_COLUMNS].sum(axis=1)
    preview["采用单价"] = float(unit_cost)
    preview["补价金额"] = preview["总件数"] * float(unit_cost)
    preview = sort_sku_rows(
        preview, material="材质", color="颜色", leading=["日期", "批次"],
        leading_ascending=[False, True],
    )
    return preview[[
        "日期", "批次", "来源", "品牌", "材质", "颜色",
        *SIZE_COLUMNS, "总件数", "采用单价", "补价金额",
    ]].reset_index(drop=True), lots.reset_index(drop=True)


def _target_keys(rows):
    data = pd.DataFrame(rows)
    return data[TARGET_IDENTITY].fillna("").astype(str).agg("||".join, axis=1)


def _common_reference_scope(selected_groups):
    if selected_groups.empty:
        return {"department": None, "category": None}
    scope = {}
    for column, argument in [("部门", "department"), ("品类", "category")]:
        values = selected_groups[column].dropna().astype(str).unique().tolist()
        scope[argument] = values[0] if len(values) == 1 else None
    return scope


def _filter_reference_scope(data, department=None, category=None):
    result = pd.DataFrame(data).copy()
    if result.empty:
        return result
    if department is not None:
        result = result[
            result["department"].fillna("").astype(str).eq(str(department))
        ]
    if category is not None:
        result = result[
            result["category"].fillna("").astype(str).eq(str(category))
        ]
    return result.copy()


def _display_value(value):
    return "—" if pd.isna(value) or not str(value).strip() else str(value)


def render_inbound_cost_editor(
    supabase, finance_df, history_cache_key=None,
):
    saved = st.session_state.pop("finance_cost_saved", None)
    if saved:
        st.success(saved)

    prepared = _prepare_inbound(finance_df)
    summary = build_cost_batch_summary(prepared)
    if summary.empty:
        st.info("当前没有需要补成本或可修改的入库批次")
        return

    st.caption(
        "先选择批次，再查看和修改该批次的 SKU 成本；缺成本批次优先显示。"
    )
    options = summary["批次键"].tolist()
    labels = {
        row["批次键"]: (
            f"{row['日期']}｜{row['来源']}｜{row['部门']} {row['品类']}｜"
            f"{int(row['SKU数']):,} SKU｜{int(row['数量']):,} 件｜{row['状态']}"
        )
        for row in summary.to_dict("records")
    }
    version = st.session_state.get("finance_cost_editor_version", 0)
    signature = sha1("|".join(options).encode()).hexdigest()[:10]
    selected = st.selectbox(
        "选择成本批次",
        options,
        format_func=lambda value: labels.get(value, value),
        key=f"finance_cost_batch_{version}_{signature}",
    )
    selected_summary = summary[summary["批次键"] == selected].iloc[0]
    metric_columns = st.columns(3)
    metric_columns[0].metric("批次 SKU", f"{int(selected_summary['SKU数']):,}")
    metric_columns[1].metric("批次数量", f"{int(selected_summary['数量']):,}")
    metric_columns[2].metric("缺成本 SKU", f"{int(selected_summary['缺成本SKU']):,}")

    inbound = _build_editor_data(
        prepared[prepared["_batch_key"] == selected]
    )
    st.markdown("#### 批次明细与价格")
    st.caption(
        "填写单位成本后，会同步修正该批次的现有库存金额和历史出库成本。"
    )
    edited = pd.DataFrame(st.data_editor(
        inbound,
        width="stretch",
        hide_index=True,
        disabled=[
            "批次ID", "日期", "来源", "部门", "品类", "品牌",
            "材质", "颜色", "尺码/型号", "数量", "成本状态",
        ],
        column_config={
            "批次ID": None,
            "日期": st.column_config.DateColumn("日期"),
            "数量": st.column_config.NumberColumn("数量", format="%d"),
            "单位成本": st.column_config.NumberColumn(
                "单位成本",
                min_value=0.0001,
                step=0.0001,
                format="$%.4f",
            ),
        },
        height=fit_table_height(inbound),
        key=f"finance_inbound_cost_editor_{version}_{signature}",
    ))
    if not st.button(
        "保存这个批次的成本",
        width="stretch",
        key=f"save_finance_cost_{version}_{signature}",
    ):
        return

    changes = find_cost_changes(inbound, edited)
    if not changes:
        st.warning("请先修改需要保存的单位成本")
        return
    source_by_record = prepared.set_index("record_id")[
        "source_type"
    ].to_dict()
    for cost_lot_id, unit_cost in changes:
        source_type = str(source_by_record.get(cost_lot_id) or "")
        kind = (
            InboundBatchKind.CONSUMABLE_MOVEMENT
            if source_type.startswith("consumable_")
            else InboundBatchKind.INVENTORY_COST_LOT
        )
        replace_inbound_batch(
            supabase,
            InboundBatchReference(kind, cost_lot_id),
            InboundCostCorrection(unit_cost),
            get_current_operator_name(),
        )
    st.session_state["finance_cost_saved"] = (
        f"已更新这个批次中 {len(changes)} 个 SKU 的成本"
    )
    st.session_state["finance_cost_editor_version"] = version + 1
    if history_cache_key:
        st.session_state.pop(history_cache_key, None)
    st.rerun()


def render_batch_cost_workspace(
    supabase,
    department,
    category="",
    *,
    inventory_domain=None,
    show_reference_fill=True,
):
    """Render the shared lazy, batch-first cost maintenance workspace."""
    scope = f"{department}|{category}|{inventory_domain or ''}"
    signature = sha1(scope.encode()).hexdigest()[:12]
    cache_key = f"inventory_cost_history_data_{signature}"
    loaded = cache_key in st.session_state

    if loaded:
        if st.button(
            "刷新入库批次成本", width="stretch",
            key=f"refresh_inventory_cost_history_{signature}",
        ):
            st.session_state.pop(cache_key, None)
            loaded = False
    elif st.button(
        "加载入库批次成本", width="stretch", type="primary",
        key=f"load_inventory_cost_history_{signature}",
    ):
        loaded = True

    if not loaded:
        st.info(
            "当前 SKU 成本已经显示。只有需要补价或修改历史入库批次时，"
            "才加载完整批次成本，避免每次刷新库存都等待。"
        )
        return

    if cache_key not in st.session_state:
        from db.finance import load_inbound_cost_history

        with st.status("正在加载入库批次成本…", expanded=True) as status:
            status.write("正在读取完整入库成本流水")
            cost_history = load_inbound_cost_history(supabase)
            if inventory_domain and "inventory_domain" in cost_history:
                cost_history = cost_history[
                    cost_history["inventory_domain"].fillna("").astype(str)
                    == str(inventory_domain)
                ].copy()
            cost_history = filter_cost_history_scope(
                cost_history, department, category
            )
            st.session_state[cache_key] = cost_history
            status.update(
                label=f"入库批次成本已加载，共 {len(cost_history):,} 条",
                state="complete", expanded=False,
            )
    cost_history = st.session_state[cache_key]
    missing_batches = build_missing_cost_batch_overview(cost_history)
    st.subheader("缺成本批次概览")
    if missing_batches.empty:
        st.success("当前范围内所有入库批次都已填写成本。")
    else:
        metric_columns = st.columns(3)
        metric_columns[0].metric("缺成本批次", f"{len(missing_batches):,}")
        metric_columns[1].metric(
            "缺成本 SKU",
            f"{int(missing_batches['缺成本 SKU 数'].sum()):,}",
        )
        metric_columns[2].metric(
            "批次原始数量",
            f"{int(missing_batches['批次数量'].sum()):,}",
        )
        st.dataframe(
            missing_batches,
            hide_index=True,
            width="stretch",
            height=fit_table_height(missing_batches),
            column_config={
                "缺成本 SKU 数": st.column_config.NumberColumn(format="%d"),
                "批次数量": st.column_config.NumberColumn(format="%d"),
            },
        )
        st.caption(
            "这里显示批次原始数量；财务汇总中的缺成本库存只统计当前尚余数量。"
        )
    st.divider()
    if show_reference_fill:
        render_reference_cost_fill(
            supabase, cost_history, history_cache_key=cache_key
        )
    st.subheader("按入库批次维护成本")
    render_inbound_cost_editor(
        supabase, cost_history, history_cache_key=cache_key
    )


def build_cost_batch_summary(finance_df):
    prepared = (
        finance_df if "_batch_key" in finance_df else _prepare_inbound(finance_df)
    )
    columns = [
        "批次键", "日期", "来源", "部门", "品类",
        "SKU数", "数量", "缺成本SKU", "状态",
    ]
    if prepared.empty:
        return pd.DataFrame(columns=columns)
    data = prepared.copy()
    costs = pd.to_numeric(data["unit_cost"], errors="coerce")
    data["_missing"] = (costs.isna() | costs.le(0)).astype(int)
    result = (
        data.groupby("_batch_key", as_index=False)
        .agg(
            date=("date", "max"),
            source_type=("source_type", "first"),
            department=("department", "first"),
            category=("category", "first"),
            sku_count=("record_id", "count"),
            quantity=("quantity", "sum"),
            missing_count=("_missing", "sum"),
        )
        .rename(columns={
            "_batch_key": "批次键", "date": "日期",
            "source_type": "来源", "department": "部门",
            "category": "品类", "sku_count": "SKU数",
            "quantity": "数量", "missing_count": "缺成本SKU",
        })
    )
    result["来源"] = result["来源"].map(SOURCE_LABELS).fillna(result["来源"])
    result["状态"] = result["缺成本SKU"].apply(
        lambda count: f"缺成本 {int(count)}" if count else "已填写"
    )
    result["_complete"] = (result["缺成本SKU"] == 0).astype(int)
    return result.sort_values(
        ["_complete", "日期"], ascending=[True, False]
    ).drop(columns=["_complete"])[columns].reset_index(drop=True)


def _prepare_inbound(finance_df):
    if finance_df.empty:
        return finance_df.copy()
    inbound = finance_df[
        (finance_df["direction"] == "入库")
        & finance_df["record_id"].notna()
    ].copy()
    if inbound.empty:
        return inbound
    batch_ids = inbound.get(
        "batch_id", pd.Series("", index=inbound.index)
    ).fillna("").astype(str)
    business_keys = inbound.get(
        "business_batch_key", pd.Series("", index=inbound.index)
    ).fillna("").astype(str)
    legacy_keys = (
        "初始化::"
        + inbound["date"].astype(str)
        + "::" + inbound["source_type"].fillna("").astype(str)
        + "::" + inbound["department"].fillna("").astype(str)
        + "::" + inbound["category"].fillna("").astype(str)
    )
    inbound["_batch_key"] = business_keys.where(
        business_keys.str.strip() != "", batch_ids
    )
    inbound["_batch_key"] = inbound["_batch_key"].where(
        inbound["_batch_key"].str.strip() != "", legacy_keys
    )
    return inbound


def find_cost_changes(original, edited):
    original_costs = original.set_index("批次ID")["单位成本"]
    changes = []
    for row in edited.to_dict("records"):
        cost_lot_id = row["批次ID"]
        new_cost = pd.to_numeric(row.get("单位成本"), errors="coerce")
        old_cost = pd.to_numeric(
            original_costs.get(cost_lot_id), errors="coerce"
        )
        if pd.isna(new_cost) or new_cost <= 0:
            continue
        if pd.isna(old_cost) or abs(float(new_cost) - float(old_cost)) > 0.00005:
            changes.append((cost_lot_id, round(float(new_cost), 4)))
    return changes


def _build_editor_data(finance_df):
    if finance_df.empty:
        return pd.DataFrame()
    inbound = _prepare_inbound(finance_df)
    if inbound.empty:
        return pd.DataFrame()
    inbound["source_type"] = inbound["source_type"].map(
        SOURCE_LABELS
    ).fillna(inbound["source_type"])
    costs = pd.to_numeric(inbound["unit_cost"], errors="coerce")
    inbound["成本状态"] = (
        costs.isna() | costs.le(0)
    ).map({True: "缺成本", False: "已填写"})
    result = inbound.rename(columns={
        "record_id": "批次ID",
        "date": "日期",
        "source_type": "来源",
        "department": "部门",
        "category": "品类",
        "brand": "品牌",
        "material": "材质",
        "color": "颜色",
        "size": "尺码/型号",
        "quantity": "数量",
        "unit_cost": "单位成本",
    })[[
        "批次ID", "日期", "来源", "部门", "品类", "品牌",
        "材质", "颜色", "尺码/型号", "数量", "成本状态", "单位成本",
    ]]
    result["_missing_order"] = (result["成本状态"] != "缺成本").astype(int)
    result = sort_sku_rows(
        result,
        leading=["_missing_order", "日期"],
        leading_ascending=[True, False],
    )
    return result.drop(columns=["_missing_order"]).reset_index(drop=True)
