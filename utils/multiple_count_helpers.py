def refresh_scgd_multiple_counts(supabase, selected_date):
    response = (
        supabase
        .rpc("refresh_scgd_multiple_counts", {"target_date": selected_date.isoformat()})
        .execute()
    )
    return response.data


def refresh_s2b_multiple_counts(supabase, selected_date):
    response = (
        supabase
        .rpc("refresh_s2b_multiple_counts", {"target_date": selected_date.isoformat()})
        .execute()
    )
    return response.data


def refresh_multiple_counts(supabase, selected_date):
    refresh_scgd_multiple_counts(supabase, selected_date)
    refresh_s2b_multiple_counts(supabase, selected_date)
