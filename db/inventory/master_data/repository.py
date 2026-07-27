import pandas as pd


SPECIFICATION_TYPES = {
    "尺码": "size",
    "型号": "model",
    "无规格": "none",
}


def load_master_data(supabase):
    departments = pd.DataFrame(
        supabase.table("inventory_departments")
        .select("id,code,name,is_active")
        .order("code")
        .execute()
        .data,
        columns=["id", "code", "name", "is_active"],
    )
    categories = pd.DataFrame(
        supabase.table("inventory_categories")
        .select("id,department_id,name,specification_type,is_active")
        .order("name")
        .execute()
        .data,
        columns=[
            "id", "department_id", "name",
            "specification_type", "is_active",
        ],
    )
    brands = pd.DataFrame(
        supabase.table("inventory_brands")
        .select("id,name,is_active")
        .order("name")
        .execute()
        .data,
        columns=["id", "name", "is_active"],
    )
    return departments, categories, brands


def create_department(supabase, code, name, created_by):
    values = {
        "code": _required(code, "部门代码"),
        "name": _required(name, "部门名称"),
        "created_by": created_by,
    }
    return supabase.table("inventory_departments").insert(values).execute().data


def create_category(
    supabase, department_id, name, specification_type, created_by
):
    values = {
        "department_id": department_id,
        "name": _required(name, "品类名称"),
        "specification_type": specification_type,
        "created_by": created_by,
    }
    return supabase.table("inventory_categories").insert(values).execute().data


def create_brand(supabase, name, created_by):
    values = {
        "name": _required(name, "品牌名称"),
        "created_by": created_by,
    }
    return supabase.table("inventory_brands").insert(values).execute().data


def load_sku_catalog(supabase, department_code):
    columns = (
        "id,sku_code,sku_name,department,category,brand,material,color,"
        "size,model,unit,quantity,is_active,category_id,brand_id"
    )
    response = (
        supabase.table("inventory_items")
        .select(columns)
        .eq("department", department_code)
        .order("category")
        .order("sku_name")
        .execute()
    )
    return pd.DataFrame(response.data)


def _required(value, label):
    result = "" if pd.isna(value) else str(value).strip()
    if not result:
        raise ValueError(f"{label}不能为空")
    return result
