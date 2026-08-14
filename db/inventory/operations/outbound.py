from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from db.inventory.core.constants import SIZE_COLUMNS
from db.inventory.core.packaging import (
    get_special_package_units,
    get_units_per_package,
)
from db.inventory.operations.outbound_specs import (
    build_outbound_sku_lookup,
    build_sku_outbound_specs,
    extract_size_box_units,
    load_container_outbound_specs,
    load_sku_outbound_specs,
)


OUTBOUND_SPECS = {
    "180g/Haloo/Box": ("Haloo", "180g", "Box"),
    "180g/Haloo/Bag": ("Haloo", "180g", "Bag"),
    "160g/Mens/Box": ("Men's", "160g", "Box"),
    "180g/SK/Box": ("SK", "180g", "Box"),
    "160g/B64/Box": ("B64", "160g", "Box"),
    "160g/Velan/Box": ("Velan", "160g", "Box"),
    "160g/T64/Box": ("T64", "160g", "Box"),
    "CVC/Haloo/Box": ("Haloo", "CVC", "Box"),
    "CVC/Haloo/Bag": ("Haloo", "CVC", "Bag"),
}


def apply_outbound_batch_date(source_df, movement_date):
    result = source_df.copy()
    result["日期"] = movement_date
    return result


def build_temporary_shortage_adjustments(issue_df, movement_date):
    columns = [
        "日期", "操作", "品牌", "材质", "颜色", "尺码", "数量", "备注",
    ]
    if issue_df.empty:
        return pd.DataFrame(columns=columns)

    result = issue_df[
        (issue_df["问题"] == "库存不足")
        & (pd.to_numeric(issue_df["缺口"], errors="coerce").fillna(0) > 0)
    ].copy()
    if result.empty:
        return pd.DataFrame(columns=columns)

    result["日期"] = movement_date
    result["操作"] = "增加"
    result["数量"] = pd.to_numeric(
        result["缺口"], errors="coerce"
    ).fillna(0).astype(int)
    result["备注"] = "临时库存调整｜每日出库缺口补足"
    return result[columns].reset_index(drop=True)


def build_outbound_package_template(outbound_specs=None):
    today = datetime.now(ZoneInfo("America/New_York")).date()
    rows = []
    for specification in (outbound_specs or OUTBOUND_SPECS):
        for color in ["黑", "白"]:
            rows.append({
                "日期": today,
                "包装规格": specification,
                "颜色": color,
                **{size: 0 for size in SIZE_COLUMNS},
                "备注": "每日正常出货",
            })
    return pd.DataFrame(rows)


def parse_outbound_package_file(uploaded_file):
    if uploaded_file.name.lower().endswith(".csv"):
        source_df = pd.read_csv(uploaded_file)
    else:
        source_df = pd.read_excel(uploaded_file)
    return normalize_outbound_packages(source_df)


def normalize_outbound_packages(source_df, outbound_specs=None):
    required = {"日期", "包装规格", "颜色", *SIZE_COLUMNS}
    missing = required - set(source_df.columns)
    if missing:
        raise ValueError(f"缺少列：{', '.join(sorted(missing))}")

    result_df = source_df.copy()
    result_df["日期"] = pd.to_datetime(result_df["日期"], errors="coerce").dt.date
    result_df["包装规格"] = result_df["包装规格"].fillna("").astype(str).str.strip()
    result_df["颜色"] = result_df["颜色"].fillna("").astype(str).str.strip()
    if "备注" not in result_df.columns:
        result_df["备注"] = "每日正常出货"
    result_df["备注"] = result_df["备注"].fillna("每日正常出货").astype(str)
    for size in SIZE_COLUMNS:
        result_df[size] = pd.to_numeric(
            result_df[size], errors="coerce"
        ).fillna(0).clip(lower=0).astype(int)
    valid_specs = outbound_specs or OUTBOUND_SPECS
    invalid_specs = sorted(set(result_df["包装规格"]) - set(valid_specs))
    if invalid_specs:
        raise ValueError(f"无法识别包装规格：{', '.join(invalid_specs)}")
    return result_df.dropna(subset=["日期"])


def convert_packages_to_adjustments(
    package_df,
    packaging_rules=None,
    sku_packaging_rules=None,
    outbound_specs=None,
):
    sku_packaging_rules = sku_packaging_rules or {}
    outbound_specs = outbound_specs or OUTBOUND_SPECS
    rows = []
    for _, source in package_df.iterrows():
        specification = outbound_specs[source["包装规格"]]
        brand, material, package_type = specification[:3]
        package_units = specification[3] if len(specification) > 3 else None
        for size in SIZE_COLUMNS:
            package_count = int(source[size])
            if package_count <= 0:
                continue
            units = package_units
            if units is None:
                units = get_special_package_units(
                    sku_packaging_rules,
                    brand,
                    material,
                    source["颜色"],
                    size,
                    package_type,
                )
            if units is None:
                units = get_units_per_package(
                    brand,
                    package_type,
                    size,
                    packaging_rules,
                )
            rows.append({
                "日期": source["日期"],
                "操作": "扣减",
                "品牌": brand,
                "材质": material,
                "颜色": source["颜色"],
                "尺码": size,
                "数量": package_count * units,
                "成本": pd.NA,
                "备注": source.get("备注", "每日正常出货") or "每日正常出货",
            })
    return pd.DataFrame(rows)


def convert_sku_package_entries(
    entry_df,
    sku_lookup,
    movement_date,
    packaging_rules=None,
    sku_packaging_rules=None,
):
    adjustment_rows = []
    preview_rows = []
    for source in pd.DataFrame(entry_df).to_dict("records"):
        sku_label = str(source.get("SKU") or "").strip()
        if not sku_label:
            sku_label = " / ".join(
                str(source.get(column) or "").strip()
                for column in ["品牌", "材质", "颜色", "尺码"]
            )
        sku = sku_lookup.get(sku_label)
        count_value = pd.to_numeric(
            source.get("包装数量"), errors="coerce"
        )
        package_count = int(count_value) if pd.notna(count_value) else 0
        package_type = str(source.get("包装单位") or "Piece").strip()
        if sku is None or package_count <= 0:
            continue
        explicit_units = pd.to_numeric(source.get("箱规"), errors="coerce")
        if package_type == "Piece":
            units = 1
        elif pd.notna(explicit_units) and explicit_units > 0:
            units = int(explicit_units)
        else:
            units = None
        if units is None:
            units = get_special_package_units(
                sku_packaging_rules,
                sku["brand"], sku["material"], sku["color"], sku["size"],
                package_type,
            )
        if units is None:
            units = get_units_per_package(
                sku["brand"], package_type, sku["size"], packaging_rules
            )
        total = package_count * units
        preview_rows.append({
            "品牌": sku["brand"],
            "材质": sku["material"],
            "颜色": sku["color"],
            "尺码": sku["size"],
            "包装单位": package_type,
            "箱规": units,
            "包装数量": package_count,
            "总件数": total,
        })
        adjustment_rows.append({
            "日期": movement_date,
            "操作": "扣减",
            "品牌": sku["brand"],
            "材质": sku["material"],
            "颜色": sku["color"],
            "尺码": sku["size"],
            "数量": total,
            "成本": pd.NA,
            "备注": "仓库每日出货",
        })
    adjustments = pd.DataFrame(adjustment_rows)
    if not adjustments.empty:
        adjustments = adjustments.groupby(
            ["日期", "操作", "品牌", "材质", "颜色", "尺码", "备注"],
            as_index=False,
            sort=False,
        )["数量"].sum()
        adjustments["成本"] = pd.NA
    return adjustments, pd.DataFrame(preview_rows)
