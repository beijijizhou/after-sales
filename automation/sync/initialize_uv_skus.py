import pandas as pd

from db.inventory.master_data import (
    create_category,
    create_skus,
    load_master_data,
)
from db.inventory.master_data.phone_cases import (
    build_phone_case_sku_rows,
)
from db.supabase_client import supabase


DEPARTMENT = "UV"
CREATED_BY = "Andy"
CATEGORY_ROWS = {
    "手机壳": build_phone_case_sku_rows(),
    "保温杯": [
        {
            "SKU 名称": "600ml 直杯保温杯",
            "品牌": "",
            "材质": "直杯",
            "颜色": "",
            "规格": "600ml",
            "单位": "个",
        },
        {
            "SKU 名称": "600ml 咖啡杯",
            "品牌": "",
            "材质": "咖啡杯",
            "颜色": "",
            "规格": "600ml",
            "单位": "个",
        },
    ],
    "木板画": [
        {
            "SKU 名称": "木板画 2030",
            "品牌": "",
            "材质": "木板",
            "颜色": "白",
            "规格": "2030",
            "单位": "件",
        },
    ],
}


def initialize_uv_skus():
    departments, categories, brands = load_master_data(supabase)
    department = departments[
        departments["code"] == DEPARTMENT
    ].iloc[0].to_dict()

    existing_categories = set(
        categories[
            categories["department_id"] == department["id"]
        ]["name"]
    )
    for category_name in CATEGORY_ROWS:
        if category_name not in existing_categories:
            create_category(
                supabase,
                department["id"],
                category_name,
                "model",
                CREATED_BY,
            )

    _, categories, brands = load_master_data(supabase)
    active_brands = brands[
        brands.get("is_active", False) == True  # noqa: E712
    ] if not brands.empty else pd.DataFrame()
    results = {}
    for category_name, rows in CATEGORY_ROWS.items():
        category = categories[
            (categories["department_id"] == department["id"])
            & (categories["name"] == category_name)
        ].iloc[0].to_dict()
        results[category_name] = create_skus(
            supabase,
            department,
            category,
            rows,
            active_brands,
            CREATED_BY,
        )
    return results


if __name__ == "__main__":
    print(initialize_uv_skus())
