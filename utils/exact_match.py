from utils.barcode_patterns import (
    build_candidate_to_inputs,
    build_embedded_key_to_inputs,
    build_exact_search_preview,
    build_order_code_to_inputs,
    build_prefix_to_inputs,
    embedded_order_inputs,
)
from utils.hansen_matcher import extract_order_key


SCAN_COLUMNS = "barcode,scanned_by,scanned_at"
PREFIX_RANGE_CHUNK = 20
PREFIX_RANGE_UPPER = "zzzzzzzz"
INPUT_CHUNK = 200
RESPONSE_ROW_LIMIT = 1000


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
    truncated = False
    for candidate_group in chunk_list(search_values, 100):
        response = (
            supabase
            .table("barcode_scans")
            .select(SCAN_COLUMNS)
            .in_("barcode", candidate_group)
            .execute()
        )
        rows = response.data or []
        truncated = truncated or len(rows) >= RESPONSE_ROW_LIMIT
        results.extend(rows)

    prefixes = tuple(search_prefixes)
    for prefix_group in chunk_list(search_prefixes, PREFIX_RANGE_CHUNK):
        response = (
            supabase
            .table("barcode_scans")
            .select(SCAN_COLUMNS)
            .or_(",".join(_prefix_range_filter(p) for p in prefix_group))
            .execute()
        )
        rows = response.data or []
        truncated = truncated or len(rows) >= RESPONSE_ROW_LIMIT
        results.extend(
            row
            for row in rows
            if str(row.get("barcode", "")).upper().startswith(prefixes)
        )
    return results, truncated


def _raw_case_values(barcodes):
    # Scans are stored as typed, so a lower-case payload only matches the
    # original spelling; candidates themselves are always upper-case.
    return [
        value.strip()
        for value in barcodes
        if value.strip() != value.strip().upper()
    ]


def _fetch(supabase, barcodes, fuzzy, state):
    search_values = [
        *build_candidate_to_inputs(barcodes),
        *_raw_case_values(barcodes),
    ]
    search_prefixes = list(build_prefix_to_inputs(barcodes, fuzzy=fuzzy))
    embedded_keys = list(build_embedded_key_to_inputs(barcodes))
    order_codes = list(build_order_code_to_inputs(barcodes))

    if state["use_rpc"]:
        try:
            response = supabase.rpc(
                "search_barcode_scans_by_candidates",
                {
                    "p_barcodes": search_values,
                    "p_prefixes": search_prefixes,
                    "p_embedded_keys": embedded_keys,
                    "p_order_codes": order_codes,
                },
            ).execute()
            rows = response.data or []
            return rows, len(rows) >= RESPONSE_ROW_LIMIT
        except Exception as error:
            if "PGRST202" not in str(error):
                raise
            state["use_rpc"] = False
    return _search_without_rpc(supabase, search_values, search_prefixes)


def _fetch_all(supabase, barcodes, fuzzy, state):
    # The API caps one response at RESPONSE_ROW_LIMIT rows; split the inputs
    # until every response is complete instead of silently dropping matches.
    rows, truncated = _fetch(supabase, barcodes, fuzzy, state)
    if not truncated or len(barcodes) <= 1:
        return rows
    middle = len(barcodes) // 2
    return [
        *_fetch_all(supabase, barcodes[:middle], fuzzy, state),
        *_fetch_all(supabase, barcodes[middle:], fuzzy, state),
    ]


def search(supabase, barcodes, fuzzy=False):
    candidate_to_inputs = build_candidate_to_inputs(barcodes)
    for value in barcodes:
        inputs = candidate_to_inputs.setdefault(value.strip().upper(), [])
        if value not in inputs:
            inputs.append(value)
    prefix_to_inputs = build_prefix_to_inputs(barcodes, fuzzy=fuzzy)
    embedded_key_to_inputs = build_embedded_key_to_inputs(barcodes)

    state = {"use_rpc": True}
    results = []
    for barcode_group in chunk_list(barcodes, INPUT_CHUNK):
        results.extend(_fetch_all(supabase, barcode_group, fuzzy, state))

    results = list({
        (row.get("barcode"), row.get("scanned_by"), row.get("scanned_at")): row
        for row in results
    }.values())

    order_code_to_inputs = build_order_code_to_inputs(barcodes)
    found_inputs = set()
    matched_results = []
    for row in results:
        candidate = str(row.get("barcode", "")).upper()
        row_inputs = set(candidate_to_inputs.get(candidate, []))
        for prefix, inputs in prefix_to_inputs.items():
            if candidate.startswith(prefix):
                row_inputs.update(inputs)
        row_inputs.update(
            embedded_key_to_inputs.get(extract_order_key(candidate), [])
        )
        row_inputs.update(embedded_order_inputs(candidate, order_code_to_inputs))
        # An order-code lookup returns every malformed scan of the order;
        # keep only the rows that really belong to a searched item.
        if row_inputs:
            matched_results.append(row)
            found_inputs.update(row_inputs)
    results = matched_results

    return results, found_inputs, build_search_preview(barcodes, fuzzy=fuzzy)
