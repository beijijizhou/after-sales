"""Container-form row models, column definitions and totals."""

import pandas as pd
import streamlit as st

from db.inventory import SIZE_COLUMNS


def empty_container_items(department):
    columns = ["品类", "材质", "品牌", "颜色"]
    columns.extend(SIZE_COLUMNS if department == "DTF" else ["型号", "数量"])
    columns.extend(["成本", "备注", "删除"])
    return pd.DataFrame(columns=columns)


def add_container_identity(items, identity, department):
    result = pd.DataFrame(items).copy()
    identity_columns = container_identity_columns(department)
    if any(not str(identity.get(column, "")).strip() for column in ["品类", "材质"]):
        return result, False
    record = {
        "品类": identity.get("品类", ""), "材质": identity.get("材质", ""),
        "品牌": identity.get("品牌", ""), "颜色": identity.get("颜色", ""),
        "成本": 0.0, "备注": "", "删除": False,
    }
    record.update(
        {size: 0 for size in SIZE_COLUMNS}
        if department == "DTF"
        else {"型号": identity.get("型号", ""), "数量": 0}
    )
    if not result.empty:
        duplicate = pd.Series(True, index=result.index)
        for column in identity_columns:
            duplicate &= result[column].fillna("").astype(str).eq(
                str(record.get(column, ""))
            )
        if duplicate.any():
            return result, False
    return pd.concat([result, pd.DataFrame([record])], ignore_index=True), True


def container_identity_columns(department):
    columns = ["品类", "品牌", "材质", "颜色"]
    return [*columns, "型号"] if department != "DTF" else columns


def build_item_column_config(department, can_view_cost):
    columns = {
        "品类": st.column_config.TextColumn("品类"),
        "品牌": st.column_config.TextColumn("品牌"),
        "材质": st.column_config.TextColumn("材质"),
        "颜色": st.column_config.TextColumn("颜色"),
        "成本": st.column_config.NumberColumn(
            "成本", min_value=0.0, step=0.0001, format="%.4f"
        ),
        "备注": st.column_config.TextColumn("SKU 备注"),
        "删除": st.column_config.CheckboxColumn("删除"),
    }
    if department == "DTF":
        columns.update({
            size: st.column_config.NumberColumn(size, min_value=0, step=1)
            for size in SIZE_COLUMNS
        })
    else:
        columns["型号"] = st.column_config.TextColumn("型号")
        columns["数量"] = st.column_config.NumberColumn("数量", min_value=0, step=1)
    if not can_view_cost:
        columns["成本"] = None
    return columns


def build_container_form_rows(
    items, shipped_date, transit_days, container_no, department,
    status, container_note,
):
    result = pd.DataFrame(items).drop(columns=["删除"], errors="ignore").copy()
    result.insert(0, "部门", department)
    result.insert(0, "货柜号", str(container_no or "").strip())
    result.insert(0, "预计运输天数", int(transit_days))
    result.insert(0, "发货日期", shipped_date)
    result["状态"] = status
    result["备注"] = result["备注"].fillna("").astype(str).str.strip()
    shared_note = str(container_note or "").strip()
    if shared_note:
        result["备注"] = result["备注"].map(
            lambda value: "；".join(filter(None, [shared_note, value]))
        )
    return result


def keep_container_items(items):
    result = pd.DataFrame(items).copy()
    if "删除" not in result:
        return result
    return result.loc[~result["删除"].fillna(False).astype(bool)].copy()


def edited_total(df):
    if "数量" in df:
        return int(pd.to_numeric(df["数量"], errors="coerce").fillna(0).sum())
    return int(sum(
        pd.to_numeric(df.get(size, 0), errors="coerce").fillna(0).sum()
        for size in SIZE_COLUMNS
    ))
