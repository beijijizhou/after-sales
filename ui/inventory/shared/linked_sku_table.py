import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS
from utils.option_values import ordered_values, unique_values
from ui.inventory.shared.hierarchy import inventory_hierarchy


def linked_sku_options(
    sku_df, material=None, brand=None, color=None,
):
    source = pd.DataFrame(sku_df).copy()
    if "is_active" in source.columns:
        source = source[source["is_active"].fillna(True).astype(bool)]
    if source.empty:
        return {"materials": [], "brands": [], "colors": [], "sizes": []}
    if material:
        source = source[source["material"] == material]
    brands = _frame_values(source, "brand")
    if brand:
        source = source[source["brand"] == brand]
    colors = ordered_values(_frame_values(source, "color"), ["黑", "白"])
    if color:
        source = source[source["color"] == color]
    sizes = ordered_values(_frame_values(source, "size"), SIZE_COLUMNS)
    return {
        "materials": _frame_values(source, "material"),
        "brands": brands,
        "colors": colors,
        "sizes": sizes,
    }


def render_linked_sku_sales_table(
    sku_df, key_prefix, combine_brands=False,
):
    row_ids_key = f"{key_prefix}_row_ids"
    next_id_key = f"{key_prefix}_next_id"
    if row_ids_key not in st.session_state:
        st.session_state[row_ids_key] = [0]
        st.session_state[next_id_key] = 1

    widths = (
        [1.3, 1.0, 0.85, 0.8, 0.9, 0.85, 0.35]
        if combine_brands
        else [1.15, 1.15, 0.8, 0.75, 0.75, 0.85, 0.8, 0.35]
    )
    headers = st.columns(widths)
    labels = (
        ["材质", "颜色", "尺码", "数量", "单价", "金额", ""]
        if combine_brands
        else ["材质", "品牌", "颜色", "尺码", "数量", "单价", "金额", ""]
    )
    for column, label in zip(
        headers, labels,
    ):
        column.markdown(f"**{label}**")

    records = []
    remove_id = None
    for row_id in list(st.session_state[row_ids_key]):
        columns = st.columns(widths, vertical_alignment="bottom")
        fields = ["material"] + ([] if combine_brands else ["brand"]) + ["color", "size"]
        values = render_linked_sku_cells(
            sku_df, columns, f"{key_prefix}_{row_id}", fields,
            {"material": "材质", "brand": "品牌", "color": "颜色", "size": "尺码"},
        )
        material, color, size = values["material"], values["color"], values["size"]
        if combine_brands:
            brand = ""
            color_column, size_column = 1, 2
            quantity_column, price_column, amount_column, remove_column = (
                3, 4, 5, 6
            )
        else:
            brand = values["brand"]
            color_column, size_column = 2, 3
            quantity_column, price_column, amount_column, remove_column = (
                4, 5, 6, 7
            )
        quantity = columns[quantity_column].number_input(
            "数量", min_value=0, step=1, label_visibility="collapsed",
            key=f"{key_prefix}_{row_id}_quantity",
        )
        unit_price = columns[price_column].number_input(
            "单价", min_value=0.0, step=0.01, format="%.2f",
            label_visibility="collapsed",
            key=f"{key_prefix}_{row_id}_unit_price",
        )
        amount = round(int(quantity) * float(unit_price), 2)
        columns[amount_column].markdown(f"${amount:,.2f}")
        if columns[remove_column].button(
            "×", key=f"{key_prefix}_{row_id}_remove",
            help="删除这一行",
        ):
            remove_id = row_id
        records.append({
            "材质": material,
            "品牌": brand,
            "颜色": color,
            "尺码": size,
            "数量": int(quantity),
            "单价": float(unit_price),
            "金额": amount,
        })

    if remove_id is not None:
        remaining = [
            value for value in st.session_state[row_ids_key]
            if value != remove_id
        ]
        if not remaining:
            next_id = int(st.session_state[next_id_key])
            remaining = [next_id]
            st.session_state[next_id_key] = next_id + 1
        st.session_state[row_ids_key] = remaining
        st.rerun()
    if st.button("+ 添加销售 SKU", key=f"{key_prefix}_add_row"):
        next_id = int(st.session_state[next_id_key])
        st.session_state[row_ids_key].append(next_id)
        st.session_state[next_id_key] = next_id + 1
        st.rerun()
    return pd.DataFrame(records)


def render_linked_sku_cells(sku_df, columns, key_prefix, fields, labels):
    """Render one table row's dependent identities from the active catalog."""
    source = pd.DataFrame(sku_df).copy()
    if "is_active" in source:
        source = source[source["is_active"].fillna(True).astype(bool)]
    values = {}
    for column, field in zip(columns, fields):
        options = (_frame_values(source, "category") if field == "category"
                   else linked_sku_options(source)[field + "s"])
        value = _linked_selectbox(column, labels[field], options,
                                  f"{key_prefix}_{field}")
        values[field] = value
        source = source[source[field] == value]
        # Changing any parent resets its child widget scope, even if an option
        # happens to be valid in both scopes.
        key_prefix += f"|{field}:{value}"
    return values


def render_linked_outbound_table(sku_lookup, key_prefix, text, compact=False):
    """Row-level linked SKU selection and package quantities in one table."""
    categories = {sku.get("category", "") for sku in sku_lookup.values()}
    category = next(iter(categories)) if len(categories) == 1 else ""
    hierarchy = inventory_hierarchy("UV" if compact else "DTF", category)
    fields = list(hierarchy.fields[1:])
    labels = dict(zip(fields, hierarchy.labels[1:]))
    widths = [1.1] * len(fields) + [0.9, 1.1, 0.9, 0.3]
    for column, label in zip(st.columns(widths),
                             [labels[key] for key in fields] + [text["package"], text["units"], text["count"], ""]):
        column.markdown(f"**{label}**")
    ids_key = f"{key_prefix}_rows"
    next_key = f"{key_prefix}_next"
    if ids_key not in st.session_state:
        st.session_state[ids_key] = [0]
        st.session_state[next_key] = 1
    frame = pd.DataFrame(list(sku_lookup.values()))
    targets = {}
    for label, sku in sku_lookup.items():
        targets.setdefault(tuple(sku.get(key, "") for key in fields), []).append(label)
    rows = []
    remove = None
    for row_id in st.session_state[ids_key]:
        columns = st.columns(widths, vertical_alignment="bottom")
        values = render_linked_sku_cells(frame, columns, f"{key_prefix}_{row_id}", fields, labels)
        identity = tuple(values[key] for key in fields)
        input_key = f"{key_prefix}_{row_id}|{identity}"
        candidates = targets.get(identity, [])
        target = candidates[0] if len(candidates) == 1 else ""
        if len(candidates) > 1:
            target = st.selectbox("该导航节点下的具体 SKU", candidates, key=f"{input_key}_leaf")
        input_key += f"|sku:{target}"
        package = _linked_selectbox(columns[-4], text["package"], list(text["packages"].values()), f"{input_key}_package")
        units = columns[-3].number_input(text["units"], min_value=0, step=1,
                    key=f"{input_key}|{package}_units", label_visibility="collapsed",
                    help="0 表示使用该 SKU 的默认包装规格；同款不同箱规请填写实际件数。")
        count = columns[-2].number_input(text["count"], min_value=0, step=1,
                    key=f"{input_key}|{package}_count", label_visibility="collapsed")
        if columns[-1].button("×", key=f"{key_prefix}_{row_id}_remove"):
            remove = row_id
        rows.append({"SKU": target, "包装单位": next(key for key, label in text["packages"].items() if label == package),
                     "箱规": units or None, "包装数量": count})
    if remove is not None:
        st.session_state[ids_key] = [value for value in st.session_state[ids_key] if value != remove]
        st.rerun()
    if st.button("+ 添加出库行", key=f"{key_prefix}_add"):
        value = st.session_state[next_key]
        st.session_state[ids_key].append(value)
        st.session_state[next_key] = value + 1
        st.rerun()
    return pd.DataFrame(rows, columns=["SKU", "包装单位", "箱规", "包装数量"])


def render_linked_outbound_scope(sku_lookup, key_prefix, text, compact=False):
    """One parent-first narrowing path for apparel and UV entry."""
    source = pd.DataFrame(list(sku_lookup.values()))
    if source.empty:
        return {}
    if "is_active" in source:
        source = source[source["is_active"].fillna(True).astype(bool)]
    if source.empty:
        return {}
    categories = set(source.get("category", []))
    category = next(iter(categories)) if len(categories) == 1 else ""
    dimensions = tuple(field for field in inventory_hierarchy("UV" if compact else "DTF", category).fields[1:] if field != "size")
    for position, dimension in enumerate(dimensions, 1):
        if dimension == "category":
            options = _frame_values(source, dimension)
            label = text.get("category_filter", "Category")
        else:
            options = linked_sku_options(source)[dimension + "s"]
            label = f"{position}. {text[dimension]}"
        if len(options) == 1:
            selected = options[0]
            st.caption(f"{label}: {selected}")
        else:
            selected = _linked_selectbox(st, label, options, f"{key_prefix}_{dimension}", visible=True)
        source = source[source[dimension] == selected]
        key_prefix += f"|{dimension}:{selected}"
    identities = set(source.index)
    return {label: sku for index, (label, sku) in enumerate(sku_lookup.items())
            if index in identities}


def _linked_selectbox(container, label, options, key, visible=False):
    if not options:
        container.text_input(
            label, value="", disabled=True, label_visibility="collapsed",
            key=f"{key}_empty",
        )
        return ""
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[0]
    return container.selectbox(
        label, options, key=key, label_visibility="visible" if visible else "collapsed",
    )


def _frame_values(frame, column):
    source = pd.DataFrame(frame)
    if source.empty or column not in source:
        return []
    return unique_values(source[column])
