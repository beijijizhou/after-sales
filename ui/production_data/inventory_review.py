import pandas as pd
import streamlit as st

from db.inventory.core.queries import load_inventory_items
from utils.erp.inventory_review import (
    build_colored_tshirt_inventory_review,
)


def render_colored_inventory_review(supabase, production_df):
    st.subheader("彩色短袖生产与库存映射")
    st.caption(
        "这是扣减前预览，不会修改库存。未匹配数据不会进入预计扣减。"
    )
    inventory = load_inventory_items(
        supabase, "DTF", "彩色短袖"
    )
    source_map, allocation = build_colored_tshirt_inventory_review(
        production_df, inventory
    )
    if source_map.empty:
        st.info("当前生产数据没有彩色短袖")
        return

    total = int(source_map["生产数量"].sum())
    unresolved = int(source_map.loc[
        source_map["映射状态"] != "已匹配", "生产数量"
    ].sum())
    planned = int(allocation.loc[
        allocation["状态"] == "可扣减", "预计扣减"
    ].sum()) if not allocation.empty else 0
    shortage = int(allocation.loc[
        allocation["状态"] == "库存不足", "预计扣减"
    ].sum()) if not allocation.empty else 0
    cols = st.columns(4)
    cols[0].metric("生产总数", f"{total:,}")
    cols[1].metric("预计扣减", f"{planned:,}")
    cols[2].metric("未映射", f"{unresolved:,}")
    cols[3].metric("库存不足", f"{shortage:,}")

    st.markdown("#### 当前映射规则")
    st.dataframe(
        pd.DataFrame([
            {
                "生产数据": "品类 = 彩色短袖",
                "库存目标": "DTF / 彩色短袖",
                "规则": "固定品类匹配",
            },
            {
                "生产数据": "浅灰",
                "库存目标": "灰色",
                "规则": "已确认颜色别名",
            },
            {
                "生产数据": "其他颜色、尺码",
                "库存目标": "同颜色、同尺码",
                "规则": "精确匹配",
            },
            {
                "生产数据": "已匹配需求",
                "库存目标": "临时进货优先",
                "规则": "不足后再使用其他品牌",
            },
        ]),
        hide_index=True,
        width="stretch",
    )

    unresolved_df = source_map[
        source_map["映射状态"] != "已匹配"
    ]
    if not unresolved_df.empty:
        st.error(
            f"有 {unresolved:,} 件生产数据尚未映射，当前不会扣库存。"
        )
        st.dataframe(
            unresolved_df,
            hide_index=True,
            width="stretch",
        )

    source_tab, allocation_tab = st.tabs([
        "生产字段映射", "预计库存扣减",
    ])
    with source_tab:
        st.dataframe(
            source_map,
            hide_index=True,
            width="stretch",
            height=min(max((len(source_map) + 1) * 35 + 8, 240), 720),
        )
    with allocation_tab:
        if allocation.empty:
            st.info("当前没有可以匹配的库存扣减")
        else:
            st.dataframe(
                allocation,
                hide_index=True,
                width="stretch",
                height=min(max((len(allocation) + 1) * 35 + 8, 240), 720),
                column_config={
                    column: st.column_config.NumberColumn(
                        column, format="%d"
                    )
                    for column in [
                        "当前库存", "预计扣减", "扣减后库存",
                    ]
                },
            )
    if unresolved or shortage:
        st.warning("检查未通过：解决未映射或库存不足后，才能扣减库存。")
    else:
        st.success("映射检查通过；当前仍是预览状态，尚未扣减库存。")
