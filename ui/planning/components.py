"""UI primitives shared by inventory and consumable planning pages."""

import pandas as pd
import streamlit as st


def render_target_days_input(
    container,
    *,
    key,
    default_days,
    max_days=180,
    step=1,
):
    return int(container.number_input(
        "目标备货天数",
        min_value=1,
        max_value=int(max_days),
        value=int(default_days),
        step=int(step),
        key=key,
        help="建议点货量会把当前库存补到可支撑该天数。",
    ))


def render_planning_summary(
    forecast_df,
    *,
    reorder_column,
    coverage_column,
    quantity_unit=None,
    unit_column=None,
    after_incoming_column=None,
    low_coverage_days=14,
):
    """Render one consistent manager summary for any planned item type."""

    summary = planning_summary_values(
        forecast_df,
        reorder_column=reorder_column,
        coverage_column=coverage_column,
        unit_column=unit_column,
        after_incoming_column=after_incoming_column,
        low_coverage_days=low_coverage_days,
    )
    if summary is None:
        return
    metrics = st.columns(4 if after_incoming_column else 3)
    metrics[0].metric("需点货 SKU", summary["reorder_skus"])
    metrics[1].metric(
        f"{int(low_coverage_days)}天内风险 SKU",
        summary["risk_skus"],
    )
    if quantity_unit:
        metrics[2].metric(
            "建议点货总量",
            f"{summary['reorder_total']:,} {quantity_unit}",
        )
    else:
        metrics[2].metric(
            "涉及库存单位",
            "、".join(summary["units"]) if summary["units"] else "未设置",
            help="不同库存单位不能直接相加；具体建议数量请查看明细。",
        )
    if after_incoming_column:
        metrics[3].metric(
            "扣除在途后仍需点货",
            f"{summary['after_incoming_total']:,} {quantity_unit}",
        )


def planning_summary_values(
    forecast_df,
    *,
    reorder_column,
    coverage_column,
    unit_column=None,
    after_incoming_column=None,
    low_coverage_days=14,
):
    forecast = pd.DataFrame(forecast_df).copy()
    if forecast.empty:
        return None
    reorder = pd.to_numeric(
        forecast.get(reorder_column), errors="coerce"
    ).fillna(0)
    coverage = pd.to_numeric(
        forecast.get(coverage_column), errors="coerce"
    )
    after_incoming = pd.to_numeric(
        forecast.get(after_incoming_column), errors="coerce"
    ).fillna(0) if after_incoming_column else pd.Series(dtype=float)
    units = []
    if unit_column and unit_column in forecast:
        units = list(dict.fromkeys(
            value
            for value in forecast[unit_column].fillna("").astype(str).str.strip()
            if value
        ))
    return {
        "reorder_skus": int(reorder.gt(0).sum()),
        "risk_skus": int(
            (coverage.notna() & coverage.lt(low_coverage_days)).sum()
        ),
        "reorder_total": int(reorder.sum()),
        "after_incoming_total": int(after_incoming.sum()),
        "units": units,
    }
