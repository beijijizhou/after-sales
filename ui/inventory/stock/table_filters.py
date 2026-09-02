import pandas as pd


def render_inventory_table_filters(
    inventory_df, visible_sizes, include_zero_stock=False,
):
    if inventory_df.empty:
        return inventory_df

    display_df = inventory_df.copy()

    if not include_zero_stock:
        if "总库存" in display_df.columns:
            total = pd.to_numeric(
                display_df["总库存"], errors="coerce"
            ).fillna(0)
        else:
            quantity_columns = [
                size for size in (visible_sizes or [])
                if size in display_df.columns
            ]
            total = (
                display_df[quantity_columns]
                .apply(pd.to_numeric, errors="coerce")
                .fillna(0)
                .sum(axis=1)
            )
        display_df = display_df.loc[total.ne(0)].copy()

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
