from utils.barcode_patterns import (
    build_candidate_to_input,
    is_exact_expansion_pattern,
)
from utils import exact_match


def normalize_search_response(response):
    if len(response) == 3:
        return response

    results, found_inputs = response
    return results, found_inputs, []


def build_search_preview(barcodes):
    exact_barcodes = [
        barcode
        for barcode in barcodes
        if is_exact_expansion_pattern(barcode)
    ]
    global_search_barcodes = [
        barcode
        for barcode in barcodes
        if not is_exact_expansion_pattern(barcode)
    ]

    rows = []
    candidate_to_input = build_candidate_to_input(exact_barcodes)
    rows.extend([
        {
            "原始输入": original_value,
            "实际查询内容": candidate,
        }
        for candidate, original_value in candidate_to_input.items()
    ])
    rows.extend([
        {
            "原始输入": barcode,
            "实际查询内容": f"%{barcode}%",
        }
        for barcode in global_search_barcodes
    ])

    return rows


def search(supabase, barcodes):
    results = []
    found_inputs = set()
    search_values = build_search_preview(barcodes)

    exact_barcodes = [
        barcode
        for barcode in barcodes
        if is_exact_expansion_pattern(barcode)
    ]
    global_search_barcodes = [
        barcode
        for barcode in barcodes
        if not is_exact_expansion_pattern(barcode)
    ]

    exact_results, exact_found_inputs, exact_search_values = normalize_search_response(
        exact_match.search(
            supabase,
            exact_barcodes
        )
    )
    results.extend(exact_results)
    found_inputs.update(exact_found_inputs)
    for barcode in global_search_barcodes:
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
