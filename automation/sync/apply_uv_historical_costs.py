from db.finance.repository import update_inbound_lot_cost
from db.inventory.master_data import create_skus, load_master_data
from db.supabase_client import supabase


TARGET_BATCH_ID = "5e77f112-cbff-5cdd-8100-093d980737ad"
CREATED_BY = "Andy"
EXACT_COSTS = [
    ("保温杯", "直杯", "", "600ML", 2.30),
    ("保温杯", "咖啡杯", "", "600ML", 2.50),
    ("铁板画", "铁牌", "白", "CHEPAI", 0.30),
    ("木板画", "挂钟", "白", "25", 0.90),
    ("铁板画", "铝牌", "白", "2030", 0.41),
    ("铁板画", "铝牌", "白", "YUAN", 0.40),
    ("木板画", "木板", "白", "2030", 0.22),
    ("铁板画", "铁牌", "白", "2030", 0.22),
    ("铁板画", "铁牌", "白", "3040", 0.65),
    ("铁板画", "铁牌", "白", "YUAN", 0.22),
    ("铁板画", "铁牌", "白", "1040", 0.26),
]
PHONE_CASE_COST = 0.15


def apply_uv_historical_costs():
    _initialize_car_plate_sku()
    cutoff = _load_target_batch_cutoff()
    items = _load_cost_items()
    updated_items = 0
    updated_lots = 0

    for item in items:
        cost = _cost_for_item(item)
        if cost is None:
            continue
        _update_item_cost(item["id"], cost)
        updated_items += 1
        lots = (
            supabase.table("inventory_cost_lots")
            .select("id")
            .eq("inventory_item_id", item["id"])
            .lt("created_at", cutoff)
            .is_("reversed_at", "null")
            .execute()
            .data
            or []
        )
        for lot in lots:
            update_inbound_lot_cost(supabase, lot["id"], cost)
            updated_lots += 1

    return {
        "cutoff": cutoff,
        "updated_items": updated_items,
        "updated_pre_batch_lots": updated_lots,
    }


def _load_target_batch_cutoff():
    rows = (
        supabase.table("inventory_movements")
        .select("created_at")
        .eq("batch_id", TARGET_BATCH_ID)
        .order("created_at")
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise ValueError(f"找不到目标批次：{TARGET_BATCH_ID}")
    return rows[0]["created_at"]


def _load_cost_items():
    return (
        supabase.table("inventory_items")
        .select("id,category,material,color,size")
        .eq("department", "UV")
        .execute()
        .data
        or []
    )


def _cost_for_item(item):
    if item["category"] == "手机壳":
        return PHONE_CASE_COST
    key = (
        item["category"],
        item["material"],
        item["color"],
        item["size"],
    )
    return next(
        (
            cost for category, material, color, size, cost in EXACT_COSTS
            if key == (category, material, color, size)
        ),
        None,
    )


def _update_item_cost(item_id, cost):
    (
        supabase.table("inventory_items")
        .update({"unit_cost": cost, "成本": cost})
        .eq("id", item_id)
        .execute()
    )


def _initialize_car_plate_sku():
    departments, categories, brands = load_master_data(supabase)
    department = departments[
        departments["code"] == "UV"
    ].iloc[0].to_dict()
    category = categories[
        (categories["department_id"] == department["id"])
        & (categories["name"] == "铁板画")
    ].iloc[0].to_dict()
    create_skus(
        supabase,
        department,
        category,
        [{
            "SKU 名称": "铁车牌",
            "品牌": "",
            "材质": "铁牌",
            "颜色": "白",
            "规格": "CHEPAI",
            "单位": "件",
        }],
        brands,
        CREATED_BY,
    )


if __name__ == "__main__":
    print(apply_uv_historical_costs())
