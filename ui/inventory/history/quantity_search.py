import pandas as pd
import streamlit as st

from ui.inventory.history.history_batches import add_movement_batch_key
from ui.inventory.history.history_tables import render_movement_table


def parse_quantity_search(value):
    cleaned = str(value or "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        quantity = int(float(cleaned))
    except ValueError:
        return None
    return quantity if quantity > 0 else None


def find_outbound_quantity_candidates(
    movement_df, target_quantity, tolerance
):
    columns = [
        "batch_key", "日期", "品类", "颜色", "匹配口径",
        "匹配数量", "与目标相差", "批次出库合计", "备注",
    ]
    if movement_df.empty or target_quantity <= 0:
        return pd.DataFrame(columns=columns)
    source = add_movement_batch_key(movement_df)
    source = source[source["quantity_change"] < 0].copy()
    if source.empty:
        return pd.DataFrame(columns=columns)
    source["outbound_quantity"] = source["quantity_change"].abs()
    lower = max(int(target_quantity) - int(tolerance), 0)
    upper = int(target_quantity) + int(tolerance)
    rows = []
    for movement_date, day_group in source.groupby(
        "movement_date", sort=False
    ):
        day_total = int(day_group["outbound_quantity"].sum())
        if lower <= day_total <= upper:
            rows.append({
                "batch_key": f"day|{movement_date}",
                "日期": movement_date,
                "品类": _join_values(day_group.get("category")),
                "颜色": _join_values(day_group.get("color")),
                "匹配口径": "当日合计",
                "匹配数量": day_total,
                "与目标相差": day_total - int(target_quantity),
                "批次出库合计": day_total,
                "备注": _join_values(day_group.get("reason")),
            })
    for batch_key, group in source.groupby("batch_key", sort=False):
        batch_total = int(group["outbound_quantity"].sum())
        individual = group[
            group["outbound_quantity"].between(lower, upper)
        ]["outbound_quantity"]
        pair_quantity = _closest_pair_quantity(
            group["outbound_quantity"], target_quantity, lower, upper
        )
        if lower <= batch_total <= upper:
            matched_quantity = batch_total
            match_kind = "批次合计"
        elif pair_quantity is not None:
            matched_quantity = pair_quantity
            match_kind = "两个 SKU 合计"
        elif not individual.empty:
            matched_quantity = int(
                individual.iloc[
                    (individual - int(target_quantity)).abs().argmin()
                ]
            )
            match_kind = "单个 SKU"
        else:
            continue
        rows.append({
            "batch_key": batch_key,
            "日期": group["movement_date"].iloc[0],
            "品类": _join_values(group.get("category")),
            "颜色": _join_values(group.get("color")),
            "匹配口径": match_kind,
            "匹配数量": matched_quantity,
            "与目标相差": matched_quantity - int(target_quantity),
            "批次出库合计": batch_total,
            "备注": _join_values(group.get("reason")),
        })
    if not rows:
        return pd.DataFrame(columns=columns)
    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values(["与目标相差", "日期"], key=_sort_difference)
        .drop_duplicates(subset=["日期"], keep="first")
        .reset_index(drop=True)
    )


def outbound_movements_for_date(movement_df, selected_date):
    if movement_df.empty or selected_date is None:
        return movement_df.iloc[0:0].copy()
    result = movement_df.copy()
    dates = pd.to_datetime(
        result.get("movement_date"), errors="coerce"
    ).dt.date
    quantities = pd.to_numeric(
        result.get("quantity_change"), errors="coerce"
    ).fillna(0)
    return result[(dates == selected_date) & quantities.lt(0)].copy()


def render_outbound_quantity_search(
    filtered_movement_df, complete_movement_df, visible_sizes=None,
    key_prefix="inventory_outbound_quantity",
):
    st.markdown("#### 按数量查找当天出库")
    st.caption(
        "输入大概件数，系统会匹配批次合计或单个 SKU；"
        "找到后显示该日期的全部出库流水。"
    )
    raw_value = st.text_input(
        "出库数量",
        placeholder="例如：20000",
        key=f"{key_prefix}_search",
    )
    target = parse_quantity_search(raw_value)
    if not str(raw_value or "").strip():
        return False
    if target is None:
        st.warning("请输入大于 0 的件数，例如 20000。")
        return True
    default_tolerance = max(100, round(target * 0.15))
    tolerance = st.number_input(
        "允许上下浮动",
        min_value=0,
        value=default_tolerance,
        step=max(100, round(target * 0.01)),
        key=f"{key_prefix}_tolerance_{target}",
        help="例如目标 20,000、浮动 2,000，会查找 18,000–22,000。",
    )
    candidates = find_outbound_quantity_candidates(
        filtered_movement_df, target, int(tolerance)
    )
    if candidates.empty:
        st.warning(
            f"没有找到 {target - int(tolerance):,}–"
            f"{target + int(tolerance):,} 件之间的出库记录。"
        )
        return True

    st.success(
        f"找到 {len(candidates):,} 笔候选，"
        f"涉及 {candidates['日期'].nunique():,} 个日期。"
    )
    st.dataframe(
        candidates.drop(columns=["batch_key"]),
        hide_index=True,
        width="stretch",
        column_config={
            "日期": st.column_config.DateColumn(),
            "匹配数量": st.column_config.NumberColumn(format="%d"),
            "与目标相差": st.column_config.NumberColumn(format="%+d"),
            "批次出库合计": st.column_config.NumberColumn(format="%d"),
        },
    )
    dates = sorted(candidates["日期"].dropna().unique(), reverse=True)
    selected_date = st.selectbox(
        "查看哪一天的全部出库",
        dates,
        format_func=lambda value: value.strftime("%Y-%m-%d"),
        key=f"{key_prefix}_result_date",
    )
    day_movements = outbound_movements_for_date(
        complete_movement_df, selected_date
    )
    total = int(pd.to_numeric(
        day_movements.get("quantity_change"), errors="coerce"
    ).fillna(0).abs().sum())
    st.metric("当天全部出库", f"{total:,} 件")
    # A quantity hit is only the locator. The result must show the complete
    # outbound day, independent of the size filter used to find that hit.
    render_movement_table(day_movements, None)
    return True


def _join_values(values):
    if values is None:
        return ""
    unique = [
        value for value in dict.fromkeys(
            str(value).strip() for value in values
        )
        if value
    ]
    return "、".join(unique)


def _sort_difference(series):
    if series.name == "与目标相差":
        return series.abs()
    return series


def _closest_pair_quantity(values, target, lower, upper):
    quantities = [int(value) for value in values]
    candidates = [
        quantities[left] + quantities[right]
        for left in range(len(quantities))
        for right in range(left + 1, len(quantities))
        if lower <= quantities[left] + quantities[right] <= upper
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda value: abs(value - int(target)))
