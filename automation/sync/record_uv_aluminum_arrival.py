from datetime import datetime
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

import pandas as pd

from db.inventory.master_data import create_skus, load_master_data
from db.inventory.operations.adjustments import apply_adjustment_rows
from db.inventory.operations.outbound_audit import verify_outbound_batch
from db.supabase_client import supabase


DEPARTMENT = "UV"
CATEGORY = "铁板画"
MATERIAL = "铝牌"
COLOR = "白"
CREATED_BY = "Andy"
BATCH_ID = str(uuid5(
    NAMESPACE_URL, "uv-aluminum-temporary-inbound-2026-07-30"
))
ARRIVAL_ROWS = [
    {
        "型号": "2030",
        "数量": 11_000,
        "备注": "临时入库｜铝牌 2030｜1托｜50箱×220片",
    },
    {
        "型号": "1040",
        "数量": 10_800,
        "备注": "临时入库｜铝牌 1040｜1托｜54箱×200片",
    },
]


def record_uv_aluminum_arrival():
    _initialize_skus()
    existing = (
        supabase.table("inventory_movements")
        .select("id")
        .eq("batch_id", BATCH_ID)
        .execute()
        .data
        or []
    )
    if existing:
        return BATCH_ID, "已存在"

    today = datetime.now(ZoneInfo("America/New_York")).date()
    rows = pd.DataFrame([
        {
            "日期": today,
            "操作": "增加",
            "品牌": "",
            "材质": MATERIAL,
            "颜色": COLOR,
            "尺码": row["型号"],
            "数量": row["数量"],
            "成本": pd.NA,
            "备注": row["备注"],
        }
        for row in ARRIVAL_ROWS
    ])
    apply_adjustment_rows(
        supabase,
        DEPARTMENT,
        CATEGORY,
        rows,
        created_by=CREATED_BY,
        source_type="bulk",
        batch_id=BATCH_ID,
    )
    row_count, saved_total, _ = verify_outbound_batch(
        supabase, BATCH_ID
    )
    expected_total = sum(row["数量"] for row in ARRIVAL_ROWS)
    if row_count != len(ARRIVAL_ROWS) or saved_total != expected_total:
        raise ValueError(
            f"临时入库核验失败：{row_count} 行 / {saved_total} 件"
        )
    return BATCH_ID, "已记录"


def _initialize_skus():
    departments, categories, brands = load_master_data(supabase)
    department = departments[
        departments["code"] == DEPARTMENT
    ].iloc[0].to_dict()
    category = categories[
        (categories["department_id"] == department["id"])
        & (categories["name"] == CATEGORY)
    ].iloc[0].to_dict()
    rows = [
        {
            "SKU 名称": f"{MATERIAL} {row['型号']}",
            "品牌": "",
            "材质": MATERIAL,
            "颜色": COLOR,
            "规格": row["型号"],
            "单位": "件",
        }
        for row in ARRIVAL_ROWS
    ]
    create_skus(
        supabase, department, category, rows, brands, CREATED_BY
    )


if __name__ == "__main__":
    print(record_uv_aluminum_arrival())
