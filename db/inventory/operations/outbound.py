from datetime import datetime
from zoneinfo import ZoneInfo
import re

import pandas as pd

from db.inventory.core.constants import SIZE_COLUMNS
from db.inventory.core.packaging import (
    get_special_package_units,
    get_units_per_package,
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


def build_outbound_sku_lookup(sku_df):
    lookup = {}
    for row in pd.DataFrame(sku_df).to_dict("records"):
        if row.get("is_active") is False:
            continue
        identity = {
            key: str(row.get(key) or "").strip()
            for key in ["brand", "material", "color", "size"]
        }
        if not all(identity.values()):
            continue
        label = " / ".join(identity.values())
        lookup[label] = identity
    return dict(sorted(lookup.items()))


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
        package_type = str(source.get("包装单位") or "Box").strip()
        if sku is None or package_count <= 0:
            continue
        explicit_units = pd.to_numeric(source.get("箱规"), errors="coerce")
        units = int(explicit_units) if pd.notna(explicit_units) and explicit_units > 0 else None
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


def load_container_outbound_specs(supabase, department, category):
    query = (
        supabase.table("inventory_container_imports")
        .select("brand,material,size,note,status")
        .eq("department", department)
        .in_("status", ["已到柜", "已到货", "已入库"])
    )
    if category:
        query = query.eq("category", category)
    rows = query.limit(5000).execute().data or []
    specs = {}
    for row in rows:
        brand = str(row.get("brand") or "").strip()
        material = str(row.get("material") or "").strip()
        if not brand or not material:
            continue
        for units in extract_size_box_units(
            row.get("note"), row.get("size")
        ):
            label = f"{material}/{brand}/Box/{units}件"
            specs[label] = (brand, material, "Box", units)
    return specs


def load_sku_outbound_specs(
    supabase, department, category, existing_specs=None,
):
    query = (
        supabase.table("inventory_items")
        .select("brand,material,is_active")
        .eq("department", department)
    )
    if category:
        query = query.eq("category", category)
    rows = query.limit(5000).execute().data or []
    return build_sku_outbound_specs(rows, existing_specs)


def build_sku_outbound_specs(rows, existing_specs=None):
    """Add a basic box option for active SKU brand/material pairs."""
    covered_pairs = {
        (str(value[0]).strip(), str(value[1]).strip())
        for value in (existing_specs or {}).values()
        if len(value) >= 2
    }
    specs = {}
    for row in rows:
        if row.get("is_active") is False:
            continue
        brand = str(row.get("brand") or "").strip()
        material = str(row.get("material") or "").strip()
        if not brand or not material or (brand, material) in covered_pairs:
            continue
        label = f"{material}/{brand}/Box"
        specs[label] = (brand, material, "Box")
    return dict(sorted(specs.items()))


def extract_size_box_units(note, size):
    note = str(note or "")
    size = str(size or "").strip().upper()
    if not note or not size:
        return []
    size_pattern = re.compile(
        rf"(?<![A-Z0-9]){re.escape(size)}\s+([^；;]+)",
        re.IGNORECASE,
    )
    match = size_pattern.search(note)
    if not match:
        return []
    return sorted({
        int(value) for value in re.findall(
            r"\d+\s*箱\s*[×xX*]\s*(\d+)\s*件", match.group(1)
        )
    })
