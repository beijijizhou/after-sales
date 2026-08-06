def refresh_multiple_counts(supabase, selected_date):
    response = (
        supabase
        .rpc(
            "refresh_barcode_multiple_counts",
            {"target_date": selected_date.isoformat()},
        )
        .execute()
    )
    return response.data
