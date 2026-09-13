"""Configured dimension paths; business values and relationships live in records."""

from dataclasses import dataclass
import json


@dataclass(frozen=True)
class DimensionHierarchy:
    fields: tuple[str, ...]
    labels: tuple[str, ...]

    def __post_init__(self):
        if not self.fields or len(self.fields) != len(self.labels):
            raise ValueError("层级字段与名称必须完整对应")
        if len(set(self.fields)) != len(self.fields):
            raise ValueError("同一条路径不能重复使用同一属性")
        if any(not value.strip() for value in (*self.fields, *self.labels)):
            raise ValueError("层级字段与名称不能为空")

    def levels(self):
        return [dict(field=field, label=label) for field, label in zip(self.fields, self.labels)]

    def narrow(self, records, selections):
        """Apply parents in path order; no material/brand-specific rules."""
        result = records
        for field in self.fields:
            values = selections.get(field, [])
            if values:
                result = result[result[field].isin(values)]
        return result


APPAREL_HIERARCHY = DimensionHierarchy(
    ("department", "category", "material", "brand", "color", "size"),
    ("部门", "品类", "材质", "品牌", "颜色", "尺码"),
)
UV_HIERARCHY = DimensionHierarchy(
    ("department", "category", "material", "size"),
    ("部门", "品类", "材质", "型号"),
)


def inventory_hierarchy(department, category="", definitions=None):
    if definitions is None:
        import streamlit as st
        definitions = st.session_state.get("sku_hierarchy_definitions", {})
    configured = definitions.get((department, category)) if category else None
    if configured:
        levels = configured["levels"]
        return DimensionHierarchy(
            ("department", "category", *(level["field"] for level in levels)),
            ("部门", "品类", *(level["label"] for level in levels)),
        )
    return UV_HIERARCHY if department == "UV" else APPAREL_HIERARCHY


def hydrate_hierarchies(supabase):
    import streamlit as st
    from db.inventory.master_data.hierarchy import load_hierarchy_definitions
    definitions, available = load_hierarchy_definitions(supabase)
    st.session_state["sku_hierarchy_definitions"] = definitions
    st.session_state["sku_hierarchy_storage_available"] = available
    return definitions, available


def hierarchy_tree_dot(records, hierarchy, *, compact=False):
    """Arbitrary-depth prefix tree, including duplicate names in different branches."""
    graph = (['digraph { rankdir=LR; nodesep=0.12; ranksep=0.3; '
              'node [shape=box, fontsize=11, margin="0.08,0.04", height=0.25]; '
              'root [shape=point, width=0.01, label=""];'] if compact else
             ['digraph { rankdir=LR; node [shape=box]; root [label="SKU"];'])
    if compact:
        from db.inventory import SIZE_COLUMNS
        from utils.option_values import ordered_values

        tree = {"children": {}, "count": 0}
        for _, row in records.iterrows():
            node = tree
            node["count"] += 1
            for field in hierarchy.fields:
                value = str(row.get(field, "") or "").strip() or "未填写"
                node = node["children"].setdefault(value, {"children": {}, "count": 0})
                node["count"] += 1

        def signature(node):
            # Ignore quantities, but require the complete descendant structure
            # to match. Equal counts alone must never imply equal SKU choices.
            return tuple(sorted((value, signature(child)) for value, child in node["children"].items()))

        def terminal_label(values, field):
            if field == "size":
                values = ordered_values(values, SIZE_COLUMNS, include_missing=False)
                if set(values) == set(SIZE_COLUMNS):
                    return "S–5XL（全尺码）"
            return " · ".join(values)

        next_node = 0

        def emit(parent, node, depth):
            nonlocal next_node
            field, label = hierarchy.fields[depth], hierarchy.labels[depth]
            children = node["children"]
            if not children:
                return
            if depth == len(hierarchy.fields) - 1:
                groups = [(list(children), node)]
            elif field == "color":
                matching = {}
                for value, child in children.items():
                    key = signature(child)
                    matching.setdefault(key, ([], child))[0].append(value)
                groups = list(matching.values())
            else:
                groups = [([value], child) for value, child in children.items()]
            for values, child in groups:
                next_node += 1
                target = f"n{next_node}"
                title = terminal_label(values, field)
                count = node["count"] if depth == len(hierarchy.fields) - 1 else sum(children[value]["count"] for value in values)
                tooltip = f"{label}：{' · '.join(values)} · {count} 个 SKU"
                graph.extend([f"{target} [label={json.dumps(title, ensure_ascii=False)}, tooltip={json.dumps(tooltip, ensure_ascii=False)}];", f"{parent} -> {target};"])
                if depth < len(hierarchy.fields) - 1:
                    # Merge matching color branches only in presentation. Keep
                    # aggregate counts for tooltips while rendering one subtree.
                    def aggregate(nodes):
                        result = {"children": {}, "count": sum(item["count"] for item in nodes)}
                        for value in nodes[0]["children"]:
                            result["children"][value] = aggregate([item["children"][value] for item in nodes])
                        return result
                    emit(target, aggregate([children[value] for value in values]), depth + 1)

        emit("root", tree, 0)
        return "\n".join([*graph, "}"])
    nodes = {(): "root"}
    counts = {}
    for _, row in records.iterrows():
        path = ()
        for field in hierarchy.fields:
            value = str(row.get(field, "") or "").strip() or "未填写"
            path += ((field, value),)
            counts[path] = counts.get(path, 0) + 1
    for _, row in records.iterrows():
        path = ()
        parent = "root"
        for field, label in zip(hierarchy.fields, hierarchy.labels):
            value = str(row.get(field, "") or "").strip() or "未填写"
            path += ((field, value),)
            if path not in nodes:
                node = f"n{len(nodes)}"
                nodes[path] = node
                title = f"{label}：{value}\n{counts[path]} 个 SKU"
                tooltip = f"{label}：{value} · {counts[path]} 个 SKU"
                graph += [f"{node} [label={json.dumps(title, ensure_ascii=False)}, tooltip={json.dumps(tooltip, ensure_ascii=False)}];", f"{parent} -> {node};"]
            parent = nodes[path]
    return "\n".join([*graph, "}"])


def render_hierarchy_guide(hierarchy):
    import streamlit as st

    with st.expander("操作等级图 · 新人指引", expanded=False):
        nodes = "\n".join(
            f'n{index} [label={json.dumps(label, ensure_ascii=False)}];'
            for index, label in enumerate(hierarchy.labels)
        )
        edges = "\n".join(
            f"n{index} -> n{index + 1};"
            for index in range(len(hierarchy.fields) - 1)
        )
        st.graphviz_chart(
            'digraph { rankdir=LR; node [shape=box, style="rounded,filled", '
            'fillcolor="#f4eee5", color="#96704c"]; ' + nodes + edges + "}",
        )
        st.caption("从左到右：先选大类，再选小类。下一级只显示上一级范围内的有效 SKU；表格中的出库选择也遵循相同等级。")
