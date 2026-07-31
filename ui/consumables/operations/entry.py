from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from db.consumables import apply_consumable_batch
from ui.consumables.units import boxes_to_base, package_size
from utils.auth import get_current_operator_name


def render_movement_entry(
    supabase, department_code, items_df, can_edit, show_cost,
    movement_options=None, title="每日耗材入库 / 领用",
):
    st.subheader(title)
    st.caption("领用代表部门内部消耗，不会进入衣服的仓库每日出货记录。")
    if not can_edit:
        st.info("当前账号只有查看权限，不能登记耗材出入库。")
        return
    active = items_df[items_df["is_active"] == True].copy()
    if active.empty:
        st.warning("请先在“SKU 管理”中建立并启用耗材 SKU。")
        return

    movement_options = movement_options or ["入库", "领用"]
    operation_col, date_col = st.columns(2)
    movement_label = (
        movement_options[0]
        if len(movement_options) == 1
        else operation_col.segmented_control(
            "操作类型", movement_options, default=movement_options[-1],
            key="consumable_movement_type",
        )
    )
    if len(movement_options) == 1:
        operation_col.text_input(
            "操作类型",
            value=movement_label,
            disabled=True,
            key=f"consumable_fixed_type_{movement_label}",
        )
    movement_date = date_col.date_input(
        "出入库日期",
        value=datetime.now(ZoneInfo("America/New_York")).date(),
        key="consumable_movement_date",
    )

    missing = active[active.apply(package_size, axis=1).isna()]
    if not missing.empty:
        st.error(
            "以下耗材尚未设置每箱数量："
            + "、".join(missing["name"].astype(str))
        )
        return
    labels, label_to_row = _build_sku_labels(active)
    columns = ["耗材 SKU", "箱数", "备注"]
    if show_cost and movement_label == "入库":
        columns.insert(3, "单位成本")
    template = pd.DataFrame([
        {
            "耗材 SKU": None,
            "箱数": 0.0,
            "单位成本": None,
            "备注": "",
        }
        for _ in range(5)
    ])[columns]
    edited = st.data_editor(
        template,
        width="stretch",
        hide_index=True,
        num_rows="dynamic",
        key=f"consumable_entry_{department_code}_{movement_label}",
        column_config={
            "耗材 SKU": st.column_config.SelectboxColumn(
                required=True, options=labels
            ),
            "箱数": st.column_config.NumberColumn(
                min_value=0.0, step=1, format="%.2f"
            ),
            "单位成本": st.column_config.NumberColumn(
                min_value=0.0, step=0.0001, format="$%.4f"
            ),
        },
    )

    try:
        rows, preview = _normalize_entry_rows(
            edited, label_to_row, show_cost and movement_label == "入库"
        )
    except ValueError as error:
        st.error(str(error))
        rows, preview = [], pd.DataFrame()

    if not preview.empty:
        st.caption("实际库存变动预览")
        st.dataframe(
            preview, width="stretch", hide_index=True,
            column_config={
                "箱数": st.column_config.NumberColumn(format="%.2f"),
                "单位成本": st.column_config.NumberColumn(format="$%.4f"),
            },
        )

    note = st.text_input("整批备注（可选）", key="consumable_batch_note")
    confirmed = st.checkbox(
        "我已核对以上耗材和数量",
        key="confirm_consumable_movement",
    )
    if st.button(
        f"确认{movement_label}",
        type="primary",
        width="stretch",
        disabled=not rows or not confirmed,
    ):
        try:
            apply_consumable_batch(
                supabase,
                department_code,
                "inbound" if movement_label == "入库" else "issue",
                movement_date,
                rows,
                get_current_operator_name(),
                note,
            )
        except Exception as error:
            st.error(f"{movement_label}失败：{error}")
            return
        st.session_state["consumable_saved_message"] = (
            f"耗材{movement_label}成功，库存已经更新。"
        )
        st.rerun()


def _build_sku_labels(items_df):
    labels = {}
    for row in items_df.to_dict("records"):
        parts = [
            row.get("category"), row.get("name"), row.get("specification"),
            row.get("brand"), row.get("base_unit"),
        ]
        label = "｜".join(str(value).strip() for value in parts if value)
        labels[label] = row
    return list(labels), labels


def _normalize_entry_rows(edited, label_to_row, include_cost):
    records, preview = [], []
    for row in edited.to_dict("records"):
        label = row.get("耗材 SKU")
        quantity = pd.to_numeric(
            row.get("箱数", row.get("数量")), errors="coerce"
        )
        if not label or pd.isna(quantity) or quantity <= 0:
            continue
        item = label_to_row[label]
        actual_quantity = boxes_to_base(quantity, item)
        if actual_quantity is None:
            raise ValueError(f"{label} 没有设置每箱数量，不能按箱录入。")
        record = {
            "item_id": item["id"],
            "quantity": actual_quantity,
            "note": row.get("备注") or "",
        }
        unit_cost = pd.to_numeric(row.get("单位成本"), errors="coerce")
        if include_cost and not pd.isna(unit_cost):
            record["unit_cost"] = float(unit_cost)
        records.append(record)
        preview.append({
            "耗材 SKU": label,
            "箱数": float(quantity),
            "换算数量": actual_quantity,
            "换算单位": item["base_unit"],
            **({"单位成本": record.get("unit_cost")} if include_cost else {}),
        })
    return records, pd.DataFrame(preview)
