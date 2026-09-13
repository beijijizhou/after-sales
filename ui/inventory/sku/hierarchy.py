"""SKU navigation design and actual catalog tree, not an inventory editor."""

import pandas as pd
import streamlit as st
from zoneinfo import ZoneInfo

from db.inventory.master_data import load_sku_catalog
from db.inventory.master_data.hierarchy import load_hierarchy_history
from ui.inventory.shared.hierarchy import (
    DimensionHierarchy, hydrate_hierarchies, inventory_hierarchy, hierarchy_tree_dot,
)
from utils.option_values import ordered_values
from utils.sku_sorting import sort_sku_rows


def render_sku_hierarchy(supabase, department, category, can_manage):
    definitions, available = hydrate_hierarchies(supabase)
    catalog = load_sku_catalog(supabase, department)
    if catalog.empty:
        st.info("当前部门暂无 SKU")
        return
    catalog = catalog.copy()
    catalog["size"] = catalog["model"].fillna(catalog["size"]).fillna("")
    catalog = sort_sku_rows(catalog, material="material", color="color", size="size")
    st.caption("树解释 SKU 的组织方式；筛选器按当前品类的层级顺序生成。改树不改 SKU 身份、库存或历史流水。")
    categories = [category] if category else ordered_values(catalog["category"], [])
    for name in categories:
        source = catalog[catalog["category"] == name]
        hierarchy = inventory_hierarchy(department, name, definitions)
        with st.expander(f"{name} · {len(source)} 个 SKU", expanded=bool(category) or len(categories) == 1):
            view_tab, history_tab = st.tabs(["等级树", "设计历史"],
                key=f"sku_tree_view_{department}_{name}", on_change="rerun")
            with view_tab:
                active = source[source["is_active"].fillna(True).astype(bool)]
                st.caption(f"当前树展示 {len(active)} 个启用 SKU；停用 SKU 保留在目录与历史中。")
                # Preserve full tree data, but choose a focused root branch to
                # avoid trying to fit thousands of leaves into one unreadable graph.
                first_field = hierarchy.fields[2]
                roots = ordered_values(active[first_field], [])
                selected = st.multiselect("展开一级节点", roots, default=roots, key=f"sku_tree_roots_{department}_{name}_{hierarchy.fields}_compact_v2")
                focused = hierarchy.narrow(active, {first_field: selected}) if selected else active.iloc[:0]
                if focused.empty:
                    st.info("选择一级节点展开完整子树")
                else:
                    local_hierarchy = DimensionHierarchy(hierarchy.fields[2:], hierarchy.labels[2:])
                    st.caption(" → ".join(local_hierarchy.labels))
                    st.graphviz_chart(hierarchy_tree_dot(focused.fillna(""), local_hierarchy, compact=True))
            with history_tab:
                if available and history_tab.open:
                    rows = load_hierarchy_history(supabase, department, name)
                    for row in rows:
                        time = pd.Timestamp(row["changed_at"]).tz_convert(ZoneInfo("America/New_York"))
                        st.write(f"版本 {row['version']} · {row['changed_by']} · {time:%Y-%m-%d %H:%M:%S %Z}")
                        if row.get("old_levels"):
                            st.caption("修改前：" + " → ".join(level["label"] for level in row["old_levels"]))
                        st.write(" → ".join(level["label"] for level in row["new_levels"]))
                    if not rows:
                        st.caption("初始结构沿用现有属性，尚无人工设计记录；不虚构历史操作人。")
