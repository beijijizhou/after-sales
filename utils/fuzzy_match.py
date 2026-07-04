def build_search_preview(barcodes):
    return [
        {
            "原始输入": barcode,
            "实际查询内容": f"%{barcode}%",
        }
        for barcode in barcodes
    ]


def search(supabase, barcodes):
    results = []
    found_inputs = set()
    search_values = build_search_preview(barcodes)

    for barcode in barcodes:
        response = (
            supabase
            .table("barcode_scans")
            .select("barcode,scanned_by,scanned_at")
            .ilike("barcode", f"%{barcode}%")
            .limit(20)
            .execute()
        )

        if response.data:
            found_inputs.add(barcode)
            results.extend(response.data)

    return results, found_inputs, search_values
