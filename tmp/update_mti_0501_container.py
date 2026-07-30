import json

from db.supabase_client import supabase


CONTAINER_KEY = "MTI/05/01"
EXPECTED = {
    ("黑", "S"): 15220,
    ("黑", "M"): 13887,
    ("黑", "L"): 14971,
    ("黑", "XL"): 8474,
    ("黑", "2XL"): 7219,
    ("黑", "3XL"): 5210,
    ("黑", "4XL"): 1433,
    ("黑", "5XL"): 1740,
    ("白", "S"): 7627,
    ("白", "M"): 6348,
    ("白", "L"): 5913,
    ("白", "XL"): 3861,
    ("白", "2XL"): 2074,
    ("白", "3XL"): 1833,
    ("白", "4XL"): 210,
    ("白", "5XL"): 290,
}
NOTE = (
    "MUSFIK装箱单 MTI/AP/04/26；对应货柜 MTI/05/01；"
    "总计901箱；总件数96310"
)


def load_rows():
    return (
        supabase.table("inventory_container_imports")
        .select(
            "id,container_key,container_no,department,category,brand,"
            "material,color,size,quantity,unit_cost,status,note"
        )
        .eq("container_key", CONTAINER_KEY)
        .order("color")
        .order("size")
        .execute()
        .data
        or []
    )


before = load_rows()
if len(before) != len(EXPECTED):
    raise ValueError(f"预检失败：预期16行，实际{len(before)}行")
actual_keys = {(row["color"], row["size"]) for row in before}
if actual_keys != set(EXPECTED):
    raise ValueError(
        f"预检失败：SKU键不一致，缺少{set(EXPECTED) - actual_keys}，"
        f"多出{actual_keys - set(EXPECTED)}"
    )
for row in before:
    if (
        row["department"] != "DTF"
        or row["category"] != "黑白短袖"
        or row["brand"] != "Men's"
        or row["material"] != "160g"
    ):
        raise ValueError(f"预检失败：货柜身份不一致：{row}")

for row in before:
    quantity = EXPECTED[(row["color"], row["size"])]
    (
        supabase.table("inventory_container_imports")
        .update({"quantity": quantity, "note": NOTE})
        .eq("id", row["id"])
        .execute()
    )

after = load_rows()
saved = {
    (row["color"], row["size"]): int(row["quantity"])
    for row in after
}
if saved != EXPECTED:
    raise ValueError(f"保存后明细不一致：{saved}")
if sum(saved.values()) != 96310:
    raise ValueError(f"保存后总数不一致：{sum(saved.values())}")
statuses = {row["status"] for row in after}
if statuses != {"未到货"}:
    raise ValueError(f"货柜状态被意外改变：{statuses}")

print(json.dumps({
    "container_key": CONTAINER_KEY,
    "rows": len(after),
    "total": sum(saved.values()),
    "status": next(iter(statuses)),
    "brand": "Men's",
    "material": "160g",
    "details": [
        {
            "color": color,
            "size": size,
            "quantity": quantity,
        }
        for (color, size), quantity in EXPECTED.items()
    ],
}, ensure_ascii=False, indent=2))
