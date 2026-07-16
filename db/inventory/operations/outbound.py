from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from db.inventory.core.constants import SIZE_COLUMNS
from db.inventory.core.packaging import get_units_per_package


OUTBOUND_SPECS = {
    "180g/Haloo/Box": ("Haloo", "180g", "Box"),
    "180g/Haloo/Bag": ("Haloo", "180g", "Bag"),
    "160g/Mens/Box": ("Men's", "160g", "Box"),
    "160g/SK/Box": ("SK", "160g", "Box"),
    "160g/B64/Box": ("B64", "160g", "Box"),
    "160g/Velan/Box": ("Velan", "160g", "Box"),
    "160g/T64/Box": ("T64", "160g", "Box"),
    "CVC/Haloo/Box": ("Haloo", "CVC", "Box"),
    "CVC/Haloo/Bag": ("Haloo", "CVC", "Bag"),
}


def build_outbound_package_template():
    today = datetime.now(ZoneInfo("America/New_York")).date()
    rows = []
    for specification in OUTBOUND_SPECS:
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


def normalize_outbound_packages(source_df):
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
    invalid_specs = sorted(set(result_df["包装规格"]) - set(OUTBOUND_SPECS))
    if invalid_specs:
        raise ValueError(f"无法识别包装规格：{', '.join(invalid_specs)}")
    return result_df.dropna(subset=["日期"])


def convert_packages_to_adjustments(package_df):
    rows = []
    for _, source in package_df.iterrows():
        brand, material, package_type = OUTBOUND_SPECS[source["包装规格"]]
        for size in SIZE_COLUMNS:
            package_count = int(source[size])
            if package_count <= 0:
                continue
            rows.append({
                "日期": source["日期"],
                "操作": "扣减",
                "品牌": brand,
                "材质": material,
                "颜色": source["颜色"],
                "尺码": size,
                "数量": package_count * get_units_per_package(
                    brand, package_type, size
                ),
                "成本": pd.NA,
                "备注": source.get("备注", "每日正常出货") or "每日正常出货",
            })
    return pd.DataFrame(rows)
