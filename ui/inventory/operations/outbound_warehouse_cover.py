"""Let the operator decide how to cover a warehouse shortage at outbound."""

from hashlib import sha1

import streamlit as st

from db.inventory.warehouses import (
    complete_cover_transfers,
    plan_outbound_cover_transfers,
)
from utils.sku_sorting import sort_sku_rows


AUTO, MANUAL, LATER = "auto", "manual", "later"
CHOICES = {
    AUTO: "系统自动生成调拨单，补足后出库",
    MANUAL: "我先去写调拨单，写完再回来出库",
    LATER: "先出库，调拨单之后再补",
}
NOTES = {
    AUTO: "系统按出库仓缺口自动生成",
    LATER: "先出库后补单｜待仓库补调拨单核对",
}


def render_warehouse_cover(shortages, balances, movement_date, warehouse):
    """Return the cover decision: blocked flag, transfer plan and note."""
    if shortages.empty:
        return {"blocked": False, "plan": None, "note": ""}
    total = int(shortages["出库仓缺口"].sum())
    st.error(
        f"{warehouse} 仓库存不足：每日出库只从 {warehouse} 仓扣减，"
        f"下面 {len(shortages)} 个 SKU 的总库存够，但货在其他仓，"
        f"{warehouse} 仓共差 {total:,} 件。请先选择处理方式。"
    )
    st.dataframe(
        _sorted(shortages).rename(
            columns={
                "数量": "出库件数", "当前库存": "总库存",
                "出库仓库存": f"{warehouse}仓库存",
                "出库仓缺口": f"{warehouse}仓缺口",
            }
        ),
        hide_index=True, width="stretch",
    )
    plan, uncovered = plan_outbound_cover_transfers(
        shortages, balances, warehouse
    )
    signature = sha1(
        shortages[["inventory_item_id", "出库仓缺口"]]
        .to_csv(index=False).encode()
    ).hexdigest()[:10]
    choice = st.radio(
        "处理方式", list(CHOICES), index=None, format_func=CHOICES.get,
        key=f"outbound_cover_{movement_date}_{signature}",
    )
    if choice is None:
        st.info("选择处理方式后才能确认出库。")
        return {"blocked": True, "plan": None, "note": ""}
    if choice == MANUAL:
        st.info(
            f"请到「仓库调拨」把至少 {total:,} 件调到 {warehouse} 仓，"
            "完成后回到这里，预览会自动更新并允许确认。本页不会保存任何数据。"
        )
        return {"blocked": True, "plan": None, "note": ""}
    if uncovered:
        st.error(
            f"其他仓的可用库存还差 {uncovered:,} 件，系统无法自动补足。"
            "请先在「仓库调拨」核对在途或待核对的数量。"
        )
        return {"blocked": True, "plan": None, "note": ""}
    if choice == LATER:
        st.warning(
            f"系统仍需要先把缺口记入 {warehouse} 仓才能扣减，所以会按下表生成"
            "一张标记为「先出库后补单」的调拨单。之后在「仓库调拨」核对："
            "实际调拨更多时只需另记多出的数量，不要重复记录下表的数量。"
        )
    else:
        st.info("确认出库时，系统会先按下表生成已完成的调拨单，再登记出库。")
    st.dataframe(
        _sorted(plan).assign(
            目标仓=warehouse
        ),
        hide_index=True, width="stretch",
    )
    note = (
        f"每日出库配套调拨｜出库日期 {movement_date}｜{NOTES[choice]}"
    )
    return {"blocked": False, "plan": plan, "note": note}


def _sorted(rows):
    return sort_sku_rows(
        rows.drop(columns=["inventory_item_id"]), style="款式", size="尺码"
    )


def apply_warehouse_cover(supabase, cover, warehouse, operated_by):
    """Create the planned transfers; return how many orders were recorded."""
    plan = cover.get("plan")
    if plan is None or plan.empty:
        return 0
    return len(complete_cover_transfers(
        supabase, plan, warehouse, cover["note"], operated_by
    ))
