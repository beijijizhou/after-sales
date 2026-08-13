from utils.barcode_patterns import (
    build_candidate_to_input,
    build_exact_search_preview,
)


def chunk_list(values, size):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def build_search_preview(barcodes):
    return build_exact_search_preview(barcodes)


def search(supabase, barcodes):
    results = []
    candidate_to_input = build_candidate_to_input(barcodes)
    search_values = list(candidate_to_input.keys())

    for candidate_group in chunk_list(search_values, 100):
        response = (
            supabase
            .table("barcode_scans")
            .select("barcode,scanned_by,scanned_at")
            .in_("barcode", candidate_group)
            .execute()
        )

        results.extend(response.data)

    found_inputs = {
        candidate_to_input[row["barcode"].upper()]
        for row in results
        if row["barcode"].upper() in candidate_to_input
    }

    return results, found_inputs, build_search_preview(barcodes)
