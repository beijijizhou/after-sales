import streamlit as st

from ui.platform.latest_cards import render_latest_platform_cards
from utils.platform_helpers import (
    build_latest_platform_barcodes,
    build_platform_barcode_detail,
    load_daily_platform_detail_rows,
    load_daily_platform_rows,
    prepare_platform_rows,
    summarize_platform_counts,
)


def render_platform_summary(supabase, selected_date):
    st.title("平台")

    try:
        raw_df = load_daily_platform_rows(
            supabase,
            selected_date,
            columns="platform,barcode,multiple_count"
        )
        if raw_df.empty:
            st.warning(f"{selected_date.isoformat()} 没有平台数据")
            st.stop()

        df = prepare_platform_rows(raw_df)
        if df.empty:
            st.warning(f"{selected_date.isoformat()} 没有平台数据")
            st.stop()

        count_df = summarize_platform_counts(df)
        st.subheader("平台产量汇总")
        st.dataframe(
            count_df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "总生产数量": st.column_config.NumberColumn("总生产数量"),
                "多件订单数量": st.column_config.NumberColumn("多件订单数量"),
                "最后扫描时间": st.column_config.TextColumn("最后扫描时间"),
                "占比": st.column_config.ProgressColumn(
                    "占比",
                    format="%.1f%%",
                    min_value=0,
                    max_value=100,
                )
            }
        )

        latest_df = build_latest_platform_barcodes(df)
        render_latest_platform_cards(latest_df)

        st.subheader("平台条码明细")
        platform_options = count_df["平台"].tolist()
        platform_key = f"platform_detail_selected_{selected_date.isoformat()}"
        if platform_key not in st.session_state:
            st.session_state[platform_key] = ""
        if st.session_state[platform_key] not in ["", *platform_options]:
            st.session_state[platform_key] = ""

        selected_platform = st.selectbox(
            "筛选平台",
            options=["", *platform_options],
            format_func=lambda value: "请选择平台" if value == "" else value,
            key=platform_key
        )
        if not selected_platform:
            st.info("请选择平台后查看条码明细")
            st.stop()

        st.caption(f"正在查询平台：{selected_platform}")

        loading_box = st.empty()
        loading_box.info("正在加载条码明细，请稍等...")

        with st.spinner("正在加载条码明细..."):
            detail_raw_df = load_daily_platform_detail_rows(
                supabase,
                selected_date,
                [selected_platform]
            )
        loading_box.success("条码明细加载完成")

        st.caption(f"数据库返回：{len(detail_raw_df)} 条")

        detail_df = build_platform_barcode_detail(
            prepare_platform_rows(detail_raw_df)
        )
        if detail_df.empty:
            st.warning("未找到所选平台的条码明细")
            st.stop()

        st.dataframe(
            detail_df,
            hide_index=True,
            use_container_width=True
        )

    except Exception as e:
        st.error(f"数据加载失败：{e}")
