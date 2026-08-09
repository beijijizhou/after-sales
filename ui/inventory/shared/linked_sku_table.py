import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS


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
    brands = _values(source, "brand")
    if brand:
        source = source[source["brand"] == brand]
    colors = _ordered(_values(source, "color"), ["黑", "白"])
    if color:
        source = source[source["color"] == color]
    sizes = _ordered(_values(source, "size"), SIZE_COLUMNS)
    return {
        "materials": _values(source, "material"),
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
        all_options = linked_sku_options(sku_df)
        material = _linked_selectbox(
            columns[0], "材质", all_options["materials"],
            f"{key_prefix}_{row_id}_material",
        )
        material_options = linked_sku_options(sku_df, material)
        if combine_brands:
            brand = ""
            color_column, size_column = 1, 2
            quantity_column, price_column, amount_column, remove_column = (
                3, 4, 5, 6
            )
            brand_options = material_options
        else:
            brand = _linked_selectbox(
                columns[1], "品牌", material_options["brands"],
                f"{key_prefix}_{row_id}_brand",
            )
            color_column, size_column = 2, 3
            quantity_column, price_column, amount_column, remove_column = (
                4, 5, 6, 7
            )
            brand_options = linked_sku_options(sku_df, material, brand)
        color = _linked_selectbox(
            columns[color_column], "颜色", brand_options["colors"],
            f"{key_prefix}_{row_id}_color",
        )
        color_options = linked_sku_options(
            sku_df, material, None if combine_brands else brand, color
        )
        size = _linked_selectbox(
            columns[size_column], "尺码", color_options["sizes"],
            f"{key_prefix}_{row_id}_size",
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


def _linked_selectbox(container, label, options, key):
    if not options:
        container.text_input(
            label, value="", disabled=True, label_visibility="collapsed",
            key=f"{key}_empty",
        )
        return ""
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[0]
    return container.selectbox(
        label, options, key=key, label_visibility="collapsed",
    )


def _values(frame, column):
    source = pd.DataFrame(frame)
    if source.empty or column not in source:
        return []
    return sorted({
        str(value).strip() for value in source[column].dropna()
        if str(value).strip()
    })


def _ordered(values, preferred):
    values = set(values)
    result = [value for value in preferred if value in values]
    return [*result, *sorted(values - set(result))]
