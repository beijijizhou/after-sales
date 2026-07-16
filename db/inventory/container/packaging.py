import pandas as pd

from db.inventory import SIZE_COLUMNS
from db.inventory.core.packaging import (
    extract_packaging_summary,
    format_box_check,
    get_default_box_units,
)


SUPPORTED_BOX_CHECKS = {("haloo", "cvc")}


def build_container_packaging_summary(display_df, container_key):
    if display_df.empty:
        return build_container_packaging_preview(display_df)
    detail = display_df[display_df["货柜记录ID"] == container_key]
    return build_container_packaging_preview(detail)


def build_container_packaging_preview(detail):
    columns = [
        "部门", "品类", "品牌", "材质", "颜色", "核对规格", "包装记录",
        *SIZE_COLUMNS, "总件数", "备注",
    ]
    if detail.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for row in detail.to_dict("records"):
        rule_key = (
            str(row.get("品牌", "")).strip().casefold(),
            str(row.get("材质", "")).strip().casefold(),
        )
        if rule_key not in SUPPORTED_BOX_CHECKS:
            continue
        units_per_box = get_default_box_units(row.get("品牌", ""))
        note = row.get("备注", "")
        result_row = {
            "部门": row.get("部门", ""),
            "品类": row.get("品类", ""),
            "品牌": row.get("品牌", ""),
            "材质": row.get("材质", ""),
            "颜色": row.get("颜色", ""),
            "核对规格": f"默认{units_per_box}件/箱",
            "包装记录": extract_packaging_summary(note),
        }
        total_quantity = 0
        for size in SIZE_COLUMNS:
            quantity_value = pd.to_numeric(row.get(size, 0), errors="coerce")
            quantity = 0 if pd.isna(quantity_value) else int(quantity_value)
            total_quantity += quantity
            result_row[size] = format_box_check(quantity, units_per_box)
        result_row["总件数"] = total_quantity
        result_row["备注"] = note
        if total_quantity > 0:
            rows.append(result_row)
    return pd.DataFrame(rows, columns=columns)
