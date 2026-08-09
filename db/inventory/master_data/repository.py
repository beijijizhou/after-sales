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


def load_materials(supabase):
    try:
        materials = pd.DataFrame(
            supabase.table("inventory_materials")
            .select("id,name,is_active")
            .order("name")
            .execute()
            .data,
            columns=["id", "name", "is_active"],
        )
        mappings = pd.DataFrame(
            supabase.table("inventory_category_materials")
            .select("category_id,material_id")
            .execute()
            .data,
            columns=["category_id", "material_id"],
        )
        return mappings.merge(
            materials, left_on="material_id", right_on="id", how="left"
        )[["id", "name", "is_active", "category_id"]]
    except Exception:
        # Keep the SKU page usable while an older deployment is applying the
        # material-master migration. Existing materials remain selectable.
        rows = (
            supabase.table("inventory_items")
            .select("material,category_id")
            .order("material")
            .execute()
            .data
        )
        values = sorted({
            (
                str(row.get("material") or "").strip(),
                row.get("category_id"),
            )
            for row in rows
            if str(row.get("material") or "").strip()
            and row.get("category_id")
        })
        return pd.DataFrame({
            "id": [None] * len(values),
            "name": [value[0] for value in values],
            "is_active": [True] * len(values),
            "category_id": [value[1] for value in values],
        })


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


def create_material(supabase, category_id, name, created_by):
    category_id = _required(category_id, "所属品类")
    name = _required(name, "材质名称")
    existing = (
        supabase.table("inventory_materials")
        .select("id")
        .ilike("name", name)
        .limit(1)
        .execute()
        .data
    )
    if existing:
        material_id = existing[0]["id"]
    else:
        created = supabase.table("inventory_materials").insert({
            "name": name,
            "created_by": created_by,
        }).execute().data
        material_id = created[0]["id"]
    values = {
        "category_id": category_id,
        "material_id": material_id,
        "created_by": created_by,
    }
    return (
        supabase.table("inventory_category_materials")
        .insert(values)
        .execute()
        .data
    )


def load_sku_catalog(supabase, department_code, active_only=False):
    columns = (
        "id,sku_code,sku_name,department,category,brand,material,color,"
        "size,model,unit,quantity,is_active,category_id,brand_id"
    )
    query = (
        supabase.table("inventory_items")
        .select(columns)
        .eq("department", department_code)
    )
    if active_only:
        query = query.eq("is_active", True)
    response = query.order("category").order("sku_name").execute()
    return pd.DataFrame(response.data)


def _required(value, label):
    result = "" if pd.isna(value) else str(value).strip()
    if not result:
        raise ValueError(f"{label}不能为空")
    return result
