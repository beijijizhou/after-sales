from utils.barcode_patterns import (
    build_candidate_to_inputs,
    build_embedded_key_to_inputs,
    build_exact_search_preview,
    build_prefix_to_inputs,
)
from utils.hansen_matcher import extract_order_key


SCAN_COLUMNS = "barcode,scanned_by,scanned_at"
PREFIX_RANGE_CHUNK = 20
PREFIX_RANGE_UPPER = "zzzzzzzz"


def chunk_list(values, size):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def build_search_preview(barcodes, fuzzy=False):
    return build_exact_search_preview(barcodes, fuzzy=fuzzy)


def _quoted(value):
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _prefix_range_filter(prefix):
    # The table collation ignores punctuation, so an anchored LIKE cannot use
    # the default index and a ","/"-" bound is unreliable. Bound the scan by
    # the alphanumeric stem and apply the exact prefix in Python afterwards.
    stem = prefix.rstrip(",-")
    return (
        f"and(barcode.gte.{_quoted(stem)},"
        f"barcode.lte.{_quoted(stem + PREFIX_RANGE_UPPER)})"
    )


def _search_without_rpc(supabase, search_values, search_prefixes):
    results = []
    for candidate_group in chunk_list(search_values, 100):
        response = (
            supabase
            .table("barcode_scans")
            .select(SCAN_COLUMNS)
            .in_("barcode", candidate_group)
            .execute()
        )
        results.extend(response.data or [])

    prefixes = tuple(search_prefixes)
    for prefix_group in chunk_list(search_prefixes, PREFIX_RANGE_CHUNK):
        response = (
            supabase
            .table("barcode_scans")
            .select(SCAN_COLUMNS)
            .or_(",".join(_prefix_range_filter(p) for p in prefix_group))
            .execute()
        )
        results.extend(
            row
            for row in response.data or []
            if str(row.get("barcode", "")).upper().startswith(prefixes)
        )
    return results


def search(supabase, barcodes, fuzzy=False):
    results = []
    candidate_to_inputs = build_candidate_to_inputs(barcodes)
    prefix_to_inputs = build_prefix_to_inputs(barcodes, fuzzy=fuzzy)
    embedded_key_to_inputs = build_embedded_key_to_inputs(barcodes)
    search_values = list(candidate_to_inputs.keys())
    search_prefixes = list(prefix_to_inputs.keys())
    embedded_keys = list(embedded_key_to_inputs.keys())

    try:
        response = supabase.rpc(
            "search_barcode_scans_by_candidates",
            {
                "p_barcodes": search_values,
                "p_prefixes": search_prefixes,
                "p_embedded_keys": embedded_keys,
            },
        ).execute()
        results.extend(response.data or [])
    except Exception as error:
        if "PGRST202" not in str(error):
            raise
        results = _search_without_rpc(
            supabase, search_values, search_prefixes
        )

    results = list({
        (row.get("barcode"), row.get("scanned_by"), row.get("scanned_at")): row
        for row in results
    }.values())

    found_inputs = set()
    for row in results:
        candidate = str(row.get("barcode", "")).upper()
        found_inputs.update(candidate_to_inputs.get(candidate, []))
        for prefix, inputs in prefix_to_inputs.items():
            if candidate.startswith(prefix):
                found_inputs.update(inputs)
        found_inputs.update(
            embedded_key_to_inputs.get(extract_order_key(candidate), [])
        )

    return results, found_inputs, build_search_preview(barcodes, fuzzy=fuzzy)
