def render_inventory_table_filters(inventory_df, visible_sizes):
    if inventory_df.empty:
        return inventory_df

    display_df = inventory_df.copy()

    fixed_columns = [
        column
        for column in ["品类", "品牌", "材质", "颜色", "型号"]
        if column in display_df.columns
    ]
    total_columns = ["总库存"] if "总库存" in display_df.columns else []
    sizes = [
        size for size in (visible_sizes or []) if size in display_df.columns
    ]
    return display_df[[*fixed_columns, *sizes, *total_columns]]
