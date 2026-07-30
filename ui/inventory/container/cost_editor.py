import pandas as pd
import streamlit as st

from db.inventory.container.costs import update_container_item_costs
from utils.auth import get_current_operator_name, has_permission


def can_edit_container_cost():
    return (
        has_permission("can_view_cost")
        and has_permission("can_edit_container")
    )


def auto_save_container_costs(
    supabase, raw_df, container_key, edited_detail_df
):
    if not can_edit_container_cost():
        return
    target = raw_df[raw_df["container_key"] == container_key].copy()
    if target.empty:
        return
    statuses = set(target["status"].fillna("").astype(str))
    if statuses & {"已入库", "取消"}:
        st.caption("该货柜已入库或已取消，成本不能直接修改。")
        return

    if edited_detail_df is None or "成本" not in edited_detail_df.columns:
        return
    edited = edited_detail_df.copy()
    edited["成本"] = pd.to_numeric(edited["成本"], errors="coerce")
    if edited["成本"].isna().any():
        st.error("成本必须是有效数字")
        return
    item_costs = {}
    identity = {
        "部门": "department", "品类": "category", "品牌": "brand",
        "材质": "material", "颜色": "color",
    }
    for row in edited.to_dict("records"):
        matches = target.copy()
        for display_column, raw_column in identity.items():
            matches = matches[
                matches[raw_column].fillna("").astype(str)
                == str(row.get(display_column) or "")
            ]
        if "型号" in row:
            matches = matches[
                matches["size"].fillna("").astype(str)
                == str(row.get("型号") or "")
            ]
        for item in matches.to_dict("records"):
            if "id" not in item:
                st.error("货柜明细缺少记录ID，请刷新页面后重试")
                return
            current = round(float(item.get("unit_cost") or 0), 4)
            desired = round(float(row["成本"]), 4)
            if current != desired:
                item_costs[str(item["id"])] = desired
    if not item_costs:
        st.caption("直接在上方明细表的“成本”列修改单价。")
        return
    try:
        result = update_container_item_costs(
            supabase,
            container_key,
            item_costs,
            get_current_operator_name(),
        )
        st.toast(f"成本已自动保存：{result['rows']} 行")
        st.rerun()
    except Exception as error:
        st.error(f"成本自动保存失败：{error}")
