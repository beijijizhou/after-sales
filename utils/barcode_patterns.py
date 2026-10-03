from utils import hansen_matcher, hum_bird_matcher, s2b_matcher


def build_barcode_candidates(value):
    if hansen_matcher.matches(value):
        return hansen_matcher.build_candidates(value)

    if hum_bird_matcher.matches(value):
        return hum_bird_matcher.build_candidates(value)

    if s2b_matcher.matches(value):
        return s2b_matcher.build_candidates(value)

    return [value.strip().upper()]


FUZZY_PREFIX_MIN_LENGTH = 4


def build_barcode_prefixes(value, fuzzy=False):
    if hansen_matcher.matches(value):
        if fuzzy:
            return hansen_matcher.build_fuzzy_prefixes(value)
        return hansen_matcher.build_prefixes(value)

    if hum_bird_matcher.matches(value):
        return hum_bird_matcher.build_prefixes(value)

    if s2b_matcher.matches(value):
        return s2b_matcher.build_prefixes(value)

    value = value.strip().upper()
    if fuzzy and len(value) >= FUZZY_PREFIX_MIN_LENGTH:
        return [value]
    return []


def build_candidate_to_input(values):
    return {
        candidate: inputs[0]
        for candidate, inputs in build_candidate_to_inputs(values).items()
    }


def build_candidate_to_inputs(values):
    candidate_to_inputs = {}

    for value in values:
        candidates = build_barcode_candidates(value)
        for candidate in candidates:
            inputs = candidate_to_inputs.setdefault(candidate, [])
            if value not in inputs:
                inputs.append(value)

    return candidate_to_inputs


def build_prefix_to_inputs(values, fuzzy=False):
    prefix_to_inputs = {}

    for value in values:
        for prefix in build_barcode_prefixes(value, fuzzy=fuzzy):
            inputs = prefix_to_inputs.setdefault(prefix, [])
            if value not in inputs:
                inputs.append(value)

    return prefix_to_inputs


def build_embedded_key_to_inputs(values):
    key_to_inputs = {}

    for value in values:
        if not hansen_matcher.matches(value):
            continue
        key = hansen_matcher.extract_order_key(value)
        inputs = key_to_inputs.setdefault(key, [])
        if value not in inputs:
            inputs.append(value)

    return key_to_inputs


def _order_code_matcher(value):
    if hansen_matcher.matches(value):
        return None
    if hum_bird_matcher.matches(value):
        return hum_bird_matcher
    if s2b_matcher.order_code(value):
        return s2b_matcher
    return None


def build_order_code_to_inputs(values):
    code_to_inputs = {}

    for value in values:
        matcher = _order_code_matcher(value)
        if matcher is None:
            continue
        inputs = code_to_inputs.setdefault(matcher.order_code(value), [])
        if value not in inputs:
            inputs.append(value)

    return code_to_inputs


def embedded_order_inputs(barcode, code_to_inputs):
    """Inputs whose order item is carried by a malformed scan payload."""
    codes = {
        *hum_bird_matcher.embedded_order_codes(barcode),
        *s2b_matcher.embedded_order_codes(barcode),
    }
    return [
        value
        for code in codes
        for value in code_to_inputs.get(code, [])
        if _order_code_matcher(value).matches_embedded(barcode, value)
    ]


def build_exact_search_preview(values, fuzzy=False):
    candidate_rows = [
        {
            "原始输入": original_value,
            "实际查询内容": candidate,
        }
        for candidate, original_value in build_candidate_to_input(values).items()
    ]
    prefix_rows = [
        {
            "原始输入": original_values[0],
            "实际查询内容": f"{prefix}*",
        }
        for prefix, original_values in build_prefix_to_inputs(
            values, fuzzy=fuzzy
        ).items()
    ]
    return candidate_rows + prefix_rows


def build_fuzzy_search_preview(values):
    return build_exact_search_preview(values, fuzzy=True)
