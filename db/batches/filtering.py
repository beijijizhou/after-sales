"""Pure active/reversed batch filtering shared by every ledger reader."""

import pandas as pd


def reversed_record_ids(records, reversal_column="reversal_of_batch_id"):
    frame = pd.DataFrame(records)
    if frame.empty or reversal_column not in frame:
        return set()
    return set(
        frame[reversal_column].dropna().astype(str).str.strip()
    ) - {""}


def filter_active_batch_records(
    records,
    *,
    id_column="id",
    reversal_column="reversal_of_batch_id",
    type_column=None,
    reversal_type="reversal",
):
    """Remove both reversal events and the original records they reverse."""
    frame = pd.DataFrame(records).copy()
    if frame.empty:
        return frame
    reversed_ids = reversed_record_ids(frame, reversal_column)
    if reversal_column in frame:
        frame = frame[frame[reversal_column].isna()]
    if id_column in frame and reversed_ids:
        frame = frame[~frame[id_column].astype(str).isin(reversed_ids)]
    if type_column and type_column in frame:
        frame = frame[
            frame[type_column].fillna("").astype(str).ne(reversal_type)
        ]
    return frame.copy()
