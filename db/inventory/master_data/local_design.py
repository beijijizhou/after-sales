"""Local-only SKU model laboratory. No inventory/database write dependency."""

import copy
import fcntl
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from utils.runtime import is_deployed_runtime

STORE_PATH = Path(__file__).resolve().parents[3] / ".local" / "sku_models.json"


def require_local_design():
    if is_deployed_runtime():
        raise PermissionError("SKU 模型设计仅在本地开放")


def validate_model(model):
    nodes = model["nodes"]
    index = {node["id"]: node for node in nodes}
    if not nodes or len(index) != len(nodes):
        raise ValueError("层级不能为空，节点标识不能重复")
    roots = [node for node in nodes if not node["parent"]]
    if len(roots) != 1:
        raise ValueError("必须且只能有一个第一层")
    for node in nodes:
        if not node["id"].strip() or not node["label"].strip():
            raise ValueError("节点标识和层级名称不能为空")
        seen = {node["id"]}
        parent = node["parent"]
        while parent:
            if parent not in index or parent in seen:
                raise ValueError("父层不存在或层级形成循环")
            seen.add(parent)
            parent = index[parent]["parent"]
    values = {value["id"]: value for value in model["values"]}
    if len(values) != len(model["values"]):
        raise ValueError("选项标识重复")
    unique = set()
    for value in values.values():
        node = index.get(value["node"])
        if not node or not value["value"].strip():
            raise ValueError("选项所属层级不存在或值为空")
        parent_value = values.get(value["parent"])
        if node["parent"]:
            if not parent_value or parent_value["node"] != node["parent"]:
                raise ValueError("已有选项与新的父子关系不匹配；请新建试验模型或先清理关联数据")
        elif value["parent"]:
            raise ValueError("第一层选项不能有父选项")
        identity = (value["node"], value["parent"], value["value"])
        if identity in unique:
            raise ValueError("同一父节点下选项不能重复")
        unique.add(identity)
    for sku in model["skus"]:
        path = sku["path"]
        if not path or any(value not in values for value in path):
            raise ValueError("SKU 路径包含失效选项")
        parent = ""
        for value in path:
            if values[value]["parent"] != parent:
                raise ValueError("SKU 路径不符合设计的父子关系")
            parent = value
        terminal = values[path[-1]]["node"]
        if any(node["parent"] == terminal for node in nodes):
            raise ValueError("SKU 必须选择到该分支的最后一层")


def read_local_design(path=None):
    require_local_design()
    target = Path(path or STORE_PATH)
    if not target.exists():
        return {"version": 0, "models": {}, "history": []}
    return json.loads(target.read_text(encoding="utf-8"))


def write_local_design(action, model_id, payload, expected_version, operator, path=None):
    require_local_design()
    if not operator or operator.strip().lower() == "system":
        raise ValueError("必须由已登录的用户操作")
    target = Path(path or STORE_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = read_local_design(target)
        if data["version"] != expected_version:
            raise ValueError("数据已被其他操作更新，请刷新后重试")
        before = copy.deepcopy(data["models"].get(model_id))
        if action == "create_model":
            model_id = str(uuid4())
            data["models"][model_id] = {
                "name": payload["name"].strip(), "nodes": payload["nodes"],
                "values": [], "skus": [],
            }
            if not data["models"][model_id]["name"]:
                raise ValueError("模型名称不能为空")
        else:
            if model_id not in data["models"]:
                raise ValueError("模型不存在")
            model = data["models"][model_id]
            if action == "save_structure":
                model["nodes"] = payload["nodes"]
            elif action == "add_option":
                model["values"].append({"id": str(uuid4()), **payload})
            elif action == "add_sku":
                if not payload["name"].strip():
                    raise ValueError("SKU 名称不能为空")
                if any(sku["path"] == payload["path"] for sku in model["skus"]):
                    raise ValueError("这条路径已存在 SKU")
                model["skus"].append({"id": str(uuid4()), **payload})
            else:
                raise ValueError("未知设计操作")
        validate_model(data["models"][model_id])
        data["version"] += 1
        data["history"].append({
            "model_id": model_id, "action": action, "version": data["version"],
            "before": before, "after": copy.deepcopy(data["models"][model_id]),
            "operator": operator, "at": datetime.now(timezone.utc).isoformat(),
        })
        descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix="sku_models_", suffix=".json")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return model_id


def model_paths(model):
    """Field IDs, not display labels, keep renamed layers and deep branches stable."""
    nodes = {node["id"]: node for node in model["nodes"]}
    values = {value["id"]: value for value in model["values"]}
    rows = []
    for sku in model["skus"]:
        row = {"_id": sku["id"], "_name": sku["name"]}
        for value_id in sku["path"]:
            value = values[value_id]
            row[value["node"]] = value["value"]
        rows.append(row)
    paths = []
    for node in model["nodes"]:
        if any(child["parent"] == node["id"] for child in model["nodes"]):
            continue
        path = [node["id"]]
        while nodes[path[-1]]["parent"]:
            path.append(nodes[path[-1]]["parent"])
        paths.append(tuple(reversed(path)))
    return rows, paths
