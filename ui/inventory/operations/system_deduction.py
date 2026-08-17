"""Shared display model for system-generated inventory deductions."""

import pandas as pd

from ui.operations import prepare_stock_change_display


def system_deduction_comparison(
    rows, *, eligible_status=None, pending_column=None,
):
    """Normalize automatic rows to the canonical stock-review contract."""
    comparison = pd.DataFrame(rows).rename(columns={
        "预计扣减": "本次变动",
        "扣减后库存": "调整后库存",
        **({pending_column: "待处理数量"} if pending_column else {}),
    })
    if "本次变动" in comparison:
        quantities = pd.to_numeric(
            comparison["本次变动"], errors="coerce"
        ).fillna(0).abs().astype(int)
        if eligible_status is not None:
            statuses = comparison.get(
                "状态", pd.Series(eligible_status, index=comparison.index)
            ).eq(eligible_status)
            quantities = quantities.where(statuses, 0)
        comparison["本次变动"] = -quantities
    if pending_column and "待处理数量" not in comparison:
        comparison["待处理数量"] = 0
    if "待处理数量" in comparison:
        comparison["待处理数量"] = pd.to_numeric(
            comparison["待处理数量"], errors="coerce"
        ).fillna(0).astype(int)
    return comparison


def system_deduction_display(
    rows, *, eligible_status=None, pending_column=None,
):
    """Compatibility display for downloads and non-interactive consumers."""
    comparison = system_deduction_comparison(
        rows,
        eligible_status=eligible_status,
        pending_column=pending_column,
    )
    if comparison.empty:
        return comparison
    if not {
        "当前库存", "本次变动", "调整后库存",
    }.issubset(comparison.columns):
        return comparison.rename(columns={"本次变动": "本次出库 (-)"})
    return prepare_stock_change_display(comparison, action="出库")[0]
