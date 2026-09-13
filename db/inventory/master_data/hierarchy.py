"""Persisted, audited navigation definitions; never mutate SKU identities."""


def load_hierarchy_definitions(supabase):
    try:
        rows = supabase.table("inventory_sku_hierarchies").select("*").execute().data or []
    except Exception as error:
        # Only an unapplied migration may use the legacy initial definition.
        if getattr(error, "code", None) in {"PGRST205", "42P01"}:
            return {}, False
        raise
    return {(row["department"], row["category"]): row for row in rows}, True


def save_hierarchy_definition(supabase, department, category, levels, version, operator):
    from db.inventory.master_data.local_design import require_local_design
    require_local_design()
    if not operator or operator == "system":
        raise ValueError("请使用已登录的操作人保存层级设计")
    return supabase.rpc("save_inventory_sku_hierarchy", {
        "p_department": department, "p_category": category,
        "p_levels": levels, "p_expected_version": version,
        "p_operator": operator,
    }).execute().data


def load_hierarchy_history(supabase, department, category):
    return supabase.table("inventory_sku_hierarchy_history").select(
        "version,old_levels,new_levels,changed_by,changed_at"
    ).eq("department", department).eq("category", category).order(
        "version", desc=True
    ).execute().data or []
