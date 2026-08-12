"""Outbound package specifications sourced from inventory and containers."""

import re


def build_outbound_sku_lookup(sku_df):
    from pandas import DataFrame

    lookup = {}
    for row in DataFrame(sku_df).to_dict("records"):
        if row.get("is_active") is False:
            continue
        identity = {
            key: str(row.get(key) or "").strip()
            for key in ["brand", "material", "color", "size"]
        }
        if all(identity.values()):
            lookup[" / ".join(identity.values())] = identity
    return dict(sorted(lookup.items()))


def load_container_outbound_specs(supabase, department, category):
    query = (
        supabase.table("inventory_container_imports")
        .select("brand,material,size,note,status")
        .eq("department", department)
        .in_("status", ["已到柜", "已到货", "已入库"])
    )
    if category:
        query = query.eq("category", category)
    specs = {}
    for row in query.limit(5000).execute().data or []:
        brand = str(row.get("brand") or "").strip()
        material = str(row.get("material") or "").strip()
        if not brand or not material:
            continue
        for units in extract_size_box_units(row.get("note"), row.get("size")):
            specs[f"{material}/{brand}/Box/{units}件"] = (
                brand, material, "Box", units,
            )
    return specs


def load_sku_outbound_specs(
    supabase, department, category, existing_specs=None,
):
    query = (
        supabase.table("inventory_items")
        .select("brand,material,is_active")
        .eq("department", department)
    )
    if category:
        query = query.eq("category", category)
    return build_sku_outbound_specs(
        query.limit(5000).execute().data or [], existing_specs
    )


def build_sku_outbound_specs(rows, existing_specs=None):
    """Add a basic box option for active SKU brand/material pairs."""
    covered_pairs = {
        (str(value[0]).strip(), str(value[1]).strip())
        for value in (existing_specs or {}).values()
        if len(value) >= 2
    }
    specs = {}
    for row in rows:
        if row.get("is_active") is False:
            continue
        brand = str(row.get("brand") or "").strip()
        material = str(row.get("material") or "").strip()
        if not brand or not material or (brand, material) in covered_pairs:
            continue
        specs[f"{material}/{brand}/Box"] = (brand, material, "Box")
    return dict(sorted(specs.items()))


def extract_size_box_units(note, size):
    note = str(note or "")
    size = str(size or "").strip().upper()
    if not note or not size:
        return []
    match = re.search(
        rf"(?<![A-Z0-9]){re.escape(size)}\s+([^；;]+)",
        note,
        re.IGNORECASE,
    )
    if not match:
        return []
    return sorted({
        int(value) for value in re.findall(
            r"\d+\s*箱\s*[×xX*]\s*(\d+)\s*件", match.group(1)
        )
    })
