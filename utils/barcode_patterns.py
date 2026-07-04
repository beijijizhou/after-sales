from utils import hum_bird_matcher, s2b_matcher


def is_exact_expansion_pattern(value):
    return (
        hum_bird_matcher.matches(value)
        or s2b_matcher.matches(value)
    )


def build_barcode_candidates(value):
    if hum_bird_matcher.matches(value):
        return hum_bird_matcher.build_candidates(value)

    if s2b_matcher.matches(value):
        return s2b_matcher.build_candidates(value)

    return [value.strip().upper()]


def build_candidate_to_input(values):
    candidate_to_input = {}

    for value in values:
        candidates = build_barcode_candidates(value)
        for candidate in candidates:
            candidate_to_input[candidate] = value

    return candidate_to_input


def build_exact_search_preview(values):
    candidate_to_input = build_candidate_to_input(values)

    return [
        {
            "原始输入": original_value,
            "实际查询内容": candidate,
        }
        for candidate, original_value in candidate_to_input.items()
    ]
