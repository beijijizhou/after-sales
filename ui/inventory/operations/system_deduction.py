"""Shared display model for system-generated inventory deductions."""

import pandas as pd


def system_deduction_display(
    rows, *, eligible_status=None, pending_column=None,
):
    """Normalize automatic deduction rows to the stock-review vocabulary."""
    display = pd.DataFrame(rows).rename(columns={
        "预计扣减": "本次出库 (-)",
        "扣减后库存": "调整后库存",
        **({pending_column: "待处理数量"} if pending_column else {}),
    })
    if "本次出库 (-)" in display:
        quantities = pd.to_numeric(
            display["本次出库 (-)"], errors="coerce"
        ).fillna(0).abs().astype(int)
        if eligible_status is not None:
            statuses = display.get(
                "状态", pd.Series(eligible_status, index=display.index)
            ).eq(eligible_status)
            quantities = quantities.where(statuses, 0)
        display["本次出库 (-)"] = -quantities
    if pending_column and "待处理数量" not in display:
        display["待处理数量"] = 0
    if "待处理数量" in display:
        display["待处理数量"] = pd.to_numeric(
            display["待处理数量"], errors="coerce"
        ).fillna(0).astype(int)
    return display
