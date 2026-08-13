"""Shared query composition for inventory business dimensions."""


def apply_inventory_dimension_filters(
    query, *, department=None, category=None, brands=None,
    materials=None, colors=None, sizes=None,
):
    if department:
        query = query.eq("department", department)
    if category:
        query = query.eq("category", category)
    for column, values in (
        ("brand", brands), ("material", materials),
        ("color", colors), ("size", sizes),
    ):
        if values:
            query = query.in_(column, list(values))
    return query
