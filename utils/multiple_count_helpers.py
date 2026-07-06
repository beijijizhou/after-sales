def refresh_multiple_counts(supabase):
    try:
        supabase.rpc("refresh_barcode_multiple_counts").execute()
        return True
    except Exception:
        return False
