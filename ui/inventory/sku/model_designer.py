"""Local metadata-driven SKU design, option entry, record entry and review."""

import json
import pandas as pd
import streamlit as st

from db.inventory.master_data.local_design import (
    read_local_design, write_local_design, model_paths, require_local_design,
)
from ui.inventory.shared.hierarchy import DimensionHierarchy, hierarchy_tree_dot
from utils.auth import get_current_operator_name
from utils.option_values import ordered_values


def _commit(data, action, model_id, payload):
    try:
        result = write_local_design(action, model_id, payload, data["version"], get_current_operator_name())
        if action == "create_model":
            st.session_state["sku_trial_model"] = result
        st.session_state["sku_trial_saved"] = "已保存本地试验数据，正式库存未变动"
        st.rerun()
    except Exception as error:
        st.error(str(error))


def _path_input(model, prefix):
    """One root-first selector, usable for both options and SKU entry."""
    nodes = model["nodes"]
    values = model["values"]
    node = next(node for node in nodes if not node["parent"])
    parent_value = ""
    selected_path = []
    scope = prefix
    while True:
        options = [value for value in values if value["node"] == node["id"] and value["parent"] == parent_value]
        lookup = {value["id"]: value["value"] for value in options}
        selected = st.selectbox(node["label"], list(lookup), index=None, format_func=lookup.get,
            placeholder="请选择；未选择时可维护这一层的选项", key=f"{scope}_{node['id']}")
        children = [child for child in nodes if child["parent"] == node["id"]]
        if not selected:
            return selected_path, node, parent_value, False
        selected_path.append(selected)
        if not children:
            return selected_path, node, parent_value, True
        if len(children) == 1:
            child = children[0]
        else:
            labels = {child["id"]: child["label"] for child in children}
            child_id = st.selectbox("下一层分支", list(labels), format_func=labels.get,
                key=f"{scope}|{selected}_branch")
            child = next(child for child in children if child["id"] == child_id)
        parent_value = selected
        scope += f"|{selected}"
        node = child


def render_local_model_designer():
    require_local_design()
    st.info("本地 SKU 模型试验：设计、选项及试验 SKU 仅保存在本机，不写正式库存、成本或权限数据。")
    if st.session_state.pop("sku_trial_saved", ""):
        st.success("已保存本地试验数据，正式库存未变动")
    data = read_local_design()
    with st.expander("新建试验模型", expanded=not data["models"]):
        with st.form("sku_trial_new_model"):
            name = st.text_input("模型名称")
            root_label = st.text_input("第一层名称", placeholder="由你定义，例如部门、产品线")
            submitted = st.form_submit_button("建立空白模型")
        if submitted:
            _commit(data, "create_model", "", {"name": name, "nodes": [{"id":"root", "parent":"", "label":root_label}]})
    if not data["models"]:
        return
    model_ids = list(data["models"])
    if st.session_state.get("sku_trial_model") not in model_ids:
        st.session_state["sku_trial_model"] = model_ids[0]
    model_id = st.selectbox("试验模型", model_ids, format_func=lambda key:data["models"][key]["name"], key="sku_trial_model")
    model = data["models"][model_id]
    scope = f"sku_trial_{model_id}_{data['version']}"
    design, options, entry, review, history = st.tabs(
        ["结构设计", "新增 SKU 选项", "新增试验 SKU", "等级树与筛选", "操作历史"],
        key=f"sku_trial_view_{model_id}", on_change="rerun")
    with design:
        st.caption("先定义第一层，再指定各层的父层。名称、深度和分支由你设计；标识保持稳定，重命名不会改变已有 SKU 身份。")
        graph = ['digraph { rankdir=LR; node [shape=box];']
        for node in model["nodes"]:
            graph.append(f'{json.dumps(node["id"])} [label={json.dumps(node["label"],ensure_ascii=False)}];')
            if node["parent"]:
                graph.append(f'{json.dumps(node["parent"])} -> {json.dumps(node["id"])};')
        st.graphviz_chart("\n".join([*graph,"}"]))
        edited = st.data_editor(pd.DataFrame(model["nodes"]), num_rows="dynamic", hide_index=True, width="stretch",
            column_config={"id":st.column_config.TextColumn("稳定标识", required=True),
                "label":st.column_config.TextColumn("层级名称", required=True),
                "parent":st.column_config.TextColumn("父层标识（第一层留空）")}, key=f"{scope}_structure")
        if st.button("保存本地结构", key=f"{scope}_save"):
            _commit(data, "save_structure", model_id, {"nodes":pd.DataFrame(edited).fillna("").to_dict("records")})
    with options:
        st.caption("按设计逐层选择父选项；选项只属于对应父节点，不再固定显示‘新增部门/品类/品牌/材质’四个入口。")
        _, node, parent_value, _ = _path_input(model, f"{scope}_options")
        with st.form(f"{scope}_add_option"):
            value = st.text_input(f"新增 {node['label']} 选项")
            submitted = st.form_submit_button("保存本地选项")
        if submitted:
            _commit(data, "add_option", model_id, {"node":node["id"], "parent":parent_value, "value":value.strip()})
    with entry:
        path, node, _, complete = _path_input(model, f"{scope}_sku")
        with st.form(f"{scope}_add_sku"):
            name = st.text_input("试验 SKU 名称")
            submitted = st.form_submit_button("保存试验 SKU", disabled=not complete)
        if submitted:
            _commit(data, "add_sku", model_id, {"name":name.strip(), "path":path})
    with review:
        rows, paths = model_paths(model)
        node_labels = {node["id"]:node["label"] for node in model["nodes"]}
        if not rows:
            st.info("先按设计录入试验 SKU，再查看真实等级树和动态筛选")
        for path in paths:
            frame = pd.DataFrame(rows)
            if not rows or any(field not in frame for field in path):
                continue
            frame = frame.dropna(subset=list(path))
            if frame.empty:
                continue
            hierarchy = DimensionHierarchy(path, tuple(node_labels[field] for field in path))
            with st.expander(" → ".join(hierarchy.labels), expanded=True):
                filtered = frame
                parent_scope = f"{scope}_{path}"
                for column, field, label in zip(st.columns(len(path)), path, hierarchy.labels):
                    values = column.multiselect(label, ordered_values(filtered[field], []), key=f"{parent_scope}_{field}")
                    filtered = hierarchy.narrow(filtered, {field:values})
                    parent_scope += repr(values)
                st.graphviz_chart(hierarchy_tree_dot(filtered, hierarchy, compact=True))
                display = filtered[["_name", *path]].rename(columns={"_name":"SKU", **node_labels})
                st.dataframe(display, hide_index=True, width="stretch", height=max(150,(len(display)+1)*35+8))
    with history:
        events = [event for event in reversed(data["history"]) if event["model_id"] == model_id]
        for event in events:
            time = pd.Timestamp(event["at"]).tz_convert("America/New_York")
            labels = {"create_model":"建立模型", "save_structure":"修改层级", "add_option":"新增选项", "add_sku":"新增 SKU"}
            with st.expander(f"v{event['version']} · {labels[event['action']]} · {event['operator']} · {time:%Y-%m-%d %H:%M:%S %Z}"):
                st.json({"修改前":event["before"],"修改后":event["after"]})
