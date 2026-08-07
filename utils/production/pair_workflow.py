import pandas as pd

from utils.production.constants import NY_TIMEZONE


def build_pair_workflow_table(rows):
    required = {
        "segment_start_at", "segment_end_at", "qa_person",
        "hotstamp_person", "scan_count",
    }
    if rows.empty or not required.issubset(rows.columns):
        return pd.DataFrame()

    prepared = rows.copy()
    prepared["segment_start"] = _to_new_york(prepared["segment_start_at"])
    prepared["segment_end"] = _to_new_york(prepared["segment_end_at"])
    prepared["qa_person"] = _clean_text(prepared["qa_person"])
    prepared["hotstamp_person"] = _clean_text(prepared["hotstamp_person"])
    prepared["scan_count"] = pd.to_numeric(
        prepared["scan_count"], errors="coerce"
    ).fillna(0).astype(int)
    prepared = prepared.dropna(subset=["segment_start", "segment_end"])
    prepared = prepared[
        (prepared["qa_person"] != "")
        & (prepared["hotstamp_person"] != "")
        & (prepared["scan_count"] > 0)
    ].sort_values(["qa_person", "segment_start", "segment_end"])
    if prepared.empty:
        return pd.DataFrame()

    person_summaries = []
    for _, person_rows in prepared.groupby("qa_person", sort=False):
        ordered = person_rows.reset_index(drop=True)
        person_summaries.append(summarize_person_workflow(ordered))
    return (
        pd.DataFrame(person_summaries)
        .sort_values(["总产量", "质检人员"], ascending=[False, True])
        .reset_index(drop=True)
    )


def build_pair_workflow_from_detail(raw_rows):
    required = {
        "id", "scanned_by", "hotstamp_by", "scanned_at",
    }
    if raw_rows.empty or not required.issubset(raw_rows.columns):
        return pd.DataFrame()

    rows = raw_rows.copy()
    rows["scanned_at"] = pd.to_datetime(
        rows["scanned_at"], errors="coerce", utc=True
    )
    rows["scanned_by"] = _clean_text(rows["scanned_by"])
    rows["hotstamp_by"] = _clean_text(rows["hotstamp_by"])
    rows = rows.dropna(subset=["scanned_at"])
    rows = rows[
        (rows["scanned_by"] != "") & (rows["hotstamp_by"] != "")
    ].sort_values(["scanned_by", "scanned_at", "id"])
    if rows.empty:
        return pd.DataFrame()

    previous_hotstamp = rows.groupby("scanned_by")["hotstamp_by"].shift()
    starts_segment = (
        previous_hotstamp.isna()
        | rows["hotstamp_by"].ne(previous_hotstamp)
    )
    rows["segment_id"] = starts_segment.groupby(rows["scanned_by"]).cumsum()
    segments = rows.groupby(
        ["scanned_by", "segment_id", "hotstamp_by"],
        as_index=False,
    ).agg(
        segment_start_at=("scanned_at", "min"),
        segment_end_at=("scanned_at", "max"),
        scan_count=("id", "size"),
    )
    return build_pair_workflow_table(segments.rename(columns={
        "scanned_by": "qa_person",
        "hotstamp_by": "hotstamp_person",
    }))


def summarize_person_workflow(segments):
    hotstamp_totals = (
        segments.groupby("hotstamp_person", as_index=False)["scan_count"].sum()
        .sort_values(
            ["scan_count", "hotstamp_person"], ascending=[False, True]
        )
    )
    return {
        "质检人员": segments.iloc[0]["qa_person"],
        "主要烫印人员": hotstamp_totals.iloc[0]["hotstamp_person"],
        "烫印人员明细": "、".join(
            f"{row.hotstamp_person} {int(row.scan_count)}"
            for row in hotstamp_totals.itertuples(index=False)
        ),
        "总产量": int(segments["scan_count"].sum()),
        "切换次数": max(len(segments) - 1, 0),
        "工作流": " → ".join(
            format_workflow_step(segment)
            for _, segment in segments.iterrows()
        ),
    }


def format_workflow_step(segment):
    return (
        f"{segment['segment_start'].strftime('%H:%M')}–"
        f"{segment['segment_end'].strftime('%H:%M')} "
        f"{segment['hotstamp_person']}"
        f"（{int(segment['scan_count'])}）"
    )


def _clean_text(values):
    return values.fillna("").astype(str).str.strip()


def _to_new_york(values):
    return pd.to_datetime(values, errors="coerce", utc=True).dt.tz_convert(
        NY_TIMEZONE
    )
