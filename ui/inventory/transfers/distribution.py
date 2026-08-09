import pandas as pd
import streamlit as st

from db.inventory.warehouses import (
    build_warehouse_distribution,
    save_location_note,
)


def render_distribution(
    supabase, warehouses, items, balances, orders, lines, can_edit,
):
    st.subheader("三仓库存分布")
    st.caption("公司总库存不变；仓库列只表示库存大概分布，在途数量单独显示。")
    distribution = build_warehouse_distribution(items, balances, orders, lines)
    filtered = render_distribution_filters(distribution)
    if filtered.empty:
        st.info("当前筛选范围没有库存 SKU。")
        return
    metrics = st.columns(5)
    for index, column in enumerate(["25仓", "60仓", "70仓", "在途/待核对", "总库存"]):
        metrics[index].metric(column, f"{int(filtered[column].sum()):,}")
    display_columns = [
        "部门", "品类", "材质", "品牌", "颜色", "尺码",
        "25仓", "60仓", "70仓", "在途/待核对", "未分配差额", "总库存",
        "25库位", "60库位", "70库位",
    ]
    height = min(max((len(filtered) + 1) * 35 + 8, 280), 900)
    st.dataframe(
        filtered[display_columns], hide_index=True, width="stretch",
        height=height, row_height=35,
        column_config={
            **{
                column: st.column_config.NumberColumn(column, format="%d")
                for column in [
                    "25仓", "60仓", "70仓", "在途/待核对",
                    "未分配差额", "总库存",
                ]
            },
            **{
                column: st.column_config.TextColumn(column, width="small")
                for column in ["材质", "品牌", "颜色", "尺码"]
            },
        },
    )
    if can_edit:
        render_location_editor(supabase, warehouses, filtered)


def render_location_editor(supabase, warehouses, filtered):
    with st.expander("更新参考库位", expanded=False):
        labels = {
            row["库存ID"]: sku_label(row)
            for row in filtered.to_dict("records")
        }
        selected_id = st.selectbox(
            "选择 SKU", list(labels), format_func=labels.get,
            key="warehouse_location_item",
        )
        warehouse_code = st.selectbox(
            "仓库", warehouses["code"].tolist(),
            key="warehouse_location_code",
        )
        current_row = filtered[filtered["库存ID"] == selected_id].iloc[0]
        location_key = f"warehouse_location_note_{selected_id}_{warehouse_code}"
        if location_key not in st.session_state:
            st.session_state[location_key] = current_row.get(
                f"{warehouse_code}库位", ""
            )
        note = st.text_input(
            "参考位置（可留空）", key=location_key,
            placeholder="例如：A区、靠门第二托",
        )
        if st.button("保存参考库位", width="stretch"):
            save_location_note(supabase, selected_id, warehouse_code, note)
            st.session_state["warehouse_transfer_saved"] = "参考库位已保存。"
            st.rerun()


def render_distribution_filters(distribution):
    source = distribution.copy()
    department = scoped_selectbox(
        "部门", source["部门"], "warehouse_distribution_department"
    )
    if department:
        source = source[source["部门"] == department]
    category = scoped_selectbox(
        "品类", source["品类"], "warehouse_distribution_category"
    )
    if category:
        source = source[source["品类"] == category]
    columns = st.columns(4)
    filters = [
        ("材质", columns[0]), ("品牌", columns[1]),
        ("颜色", columns[2]), ("尺码", columns[3]),
    ]
    for name, container in filters:
        value = scoped_selectbox(
            name, source[name], f"warehouse_distribution_{name}", container
        )
        if value:
            source = source[source[name] == value]
    search = st.text_input(
        "模糊搜索 SKU", key="warehouse_distribution_search",
        placeholder="输入材质、品牌、颜色或尺码",
    ).strip().casefold()
    if search:
        searchable = source[["材质", "品牌", "颜色", "尺码"]].fillna("")
        matches = searchable.astype(str).agg(" ".join, axis=1).str.casefold()
        source = source[matches.str.contains(search, regex=False)]
    return source.reset_index(drop=True)


def scoped_selectbox(label, values, key, container=None):
    options = ["", *sorted({
        str(value).strip() for value in pd.Series(values).dropna()
        if str(value).strip()
    })]
    if st.session_state.get(key) not in options:
        st.session_state[key] = ""
    target = container if container is not None else st
    return target.selectbox(
        label, options, key=key,
        format_func=lambda value: "全部" if not value else value,
    )


def sku_label(row):
    return " / ".join(filter(None, [
        str(row.get("部门") or ""), str(row.get("品类") or ""),
        str(row.get("材质") or ""), str(row.get("品牌") or ""),
        str(row.get("颜色") or ""), str(row.get("尺码") or ""),
    ]))
