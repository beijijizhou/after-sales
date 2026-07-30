import streamlit as st


def render_outbound_preview_summary(adjustment_df, text):
    total = int(adjustment_df["数量"].sum())
    date_count = adjustment_df["日期"].nunique()
    with st.container(border=True):
        st.markdown(f"**{text['preview_check']}**")
        columns = st.columns(3)
        columns[0].metric(text["submitted_total"], f"{total:,}")
        columns[1].metric(text["detail_rows"], f"{len(adjustment_df):,}")
        columns[2].metric(text["outbound_dates"], f"{date_count:,}")
    return total


def render_outbound_audit(audit, mismatches, text):
    message = (
        text["audit_passed"] if audit["passed"] else text["audit_failed"]
    )
    (st.success if audit["passed"] else st.error)(message)
    with st.container(border=True):
        columns = st.columns(4)
        columns[0].metric(
            text["submitted_total"], f"{audit['expected_total']:,}"
        )
        columns[1].metric(
            text["database_total"], f"{audit['saved_total']:,}"
        )
        columns[2].metric(
            text["difference"],
            f"{audit['difference']:+,}",
        )
        columns[3].metric(
            text["row_check"],
            text["row_match"] if audit["rows_match"] else text["row_mismatch"],
        )
        st.caption(
            f"{text['detail_rows']}: "
            f"{audit['expected_row_count']:,} / {audit['saved_row_count']:,}"
        )
    if mismatches is not None and not mismatches.empty:
        st.markdown(f"**{text['mismatch_details']}**")
        st.dataframe(mismatches, hide_index=True, width="stretch")


def store_outbound_audit_feedback(audit):
    st.session_state["outbound_audit_feedback"] = audit


def render_saved_outbound_audit_feedback(text):
    audit = st.session_state.pop("outbound_audit_feedback", None)
    if audit:
        render_outbound_audit(audit, None, text)
