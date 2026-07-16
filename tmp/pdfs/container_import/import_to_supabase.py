import csv
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from db.supabase_client import supabase


PREVIEW_PATH = PROJECT_ROOT / "output/container/唐人街T恤货柜_货柜安排预览.csv"
SIZES = ["S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]


with PREVIEW_PATH.open(encoding="utf-8", newline="") as file:
    source_rows = list(csv.DictReader(file))

container_numbers = sorted({row["货柜号"] for row in source_rows})
existing_response = (
    supabase.table("inventory_container_imports")
    .select("container_no")
    .in_("container_no", container_numbers)
    .execute()
)
existing_containers = {
    row["container_no"]
    for row in existing_response.data
    if row.get("container_no")
}

records = []
for row in source_rows:
    if row["货柜号"] in existing_containers:
        continue
    for size in SIZES:
        quantity = int(row[size])
        if quantity <= 0:
            continue
        records.append({
            "shipped_date": row["发货日期"],
            "expected_arrival_date": row["预计到货日期"],
            "container_no": row["货柜号"],
            "department": row["部门"],
            "category": row["品类"] or None,
            "brand": row["品牌"],
            "material": row["材质"],
            "color": row["颜色"],
            "size": size,
            "quantity": quantity,
            "unit_cost": float(row["成本"]),
            "品牌": row["品牌"],
            "材质": row["材质"],
            "成本": float(row["成本"]),
            "status": row["状态"],
            "note": row["备注"],
        })

if records:
    supabase.table("inventory_container_imports").insert(records).execute()

verify_response = (
    supabase.table("inventory_container_imports")
    .select("container_no,quantity")
    .in_("container_no", container_numbers)
    .execute()
)
print({
    "inserted_rows": len(records),
    "skipped_containers": sorted(existing_containers),
    "verified_rows": len(verify_response.data),
    "verified_quantity": sum(int(row["quantity"]) for row in verify_response.data),
})
