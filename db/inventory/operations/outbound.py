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
