"""Bind explicit literal inputs in an exported local H3 API graph; never submit it."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def is_link(value):
    return isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and type(value[1]) is int


def iter_links(value):
    if is_link(value):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from iter_links(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_links(child)


def validate_graph(graph, info, output_node):
    if not isinstance(graph, dict) or not graph or "nodes" in graph or "links" in graph:
        raise ValueError("Expected an exported API node map, not a UI workflow")
    for node_id, node in graph.items():
        if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict) or node.get("class_type") not in info:
            raise ValueError(f"{node_id}: invalid node or class_type missing from object_info")
        meta = info[node["class_type"]]
        if meta.get("api_node") or "comfy_api_nodes" in meta.get("python_module", "") or meta.get("category", "").startswith("partner/"):
            raise ValueError(f"{node_id}: hosted/API node is outside the local H3 route")
    if output_node not in graph or not info[graph[output_node]["class_type"]].get("output_node"):
        raise ValueError("output_node must be the ID of a real terminal saver")
    edges = {}
    for node_id, node in graph.items():
        meta = info[node["class_type"]]
        required = meta.get("input", {}).get("required", {})
        missing = set(required) - set(node["inputs"])
        if missing:
            raise ValueError(f"{node_id}: missing required inputs {sorted(missing)}")
        definitions = {**required, **meta.get("input", {}).get("optional", {})}
        edges[node_id] = []
        for key, value in node["inputs"].items():
            for source, slot in iter_links(value):
                if source not in graph:
                    raise ValueError(f"{node_id}.{key}: broken link to {source}")
                outputs = info[graph[source]["class_type"]].get("output", [])
                if slot < 0 or slot >= len(outputs):
                    raise ValueError(f"{node_id}.{key}: invalid output slot {slot}")
                edges[node_id].append(source)
            spec = definitions.get(key)
            if not spec or is_link(value):
                continue  # V3 dynamic inputs still need the server's validation.
            kind = spec[0]
            opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            choices = kind if isinstance(kind, list) else opts.get("options") if kind == "COMBO" else None
            if choices is not None and value not in choices:
                raise ValueError(f"{node_id}.{key}: value/model is not an available option")
            if kind == "INT" and type(value) is not int:
                raise ValueError(f"{node_id}.{key}: expected integer")
            if kind in ("INT", "FLOAT"):
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError(f"{node_id}.{key}: expected finite number")
                if value < opts.get("min", -math.inf) or value > opts.get("max", math.inf):
                    raise ValueError(f"{node_id}.{key}: value outside node range")
            if kind == "STRING" and not isinstance(value, str):
                raise ValueError(f"{node_id}.{key}: expected string")
            if kind == "BOOLEAN" and type(value) is not bool:
                raise ValueError(f"{node_id}.{key}: expected boolean")
    visited, visiting = set(), set()

    def visit(node_id):
        if node_id in visiting:
            raise ValueError("Cycle in workflow")
        if node_id in visited:
            return
        visiting.add(node_id)
        for parent in edges[node_id]:
            visit(parent)
        visiting.remove(node_id)
        visited.add(node_id)

    visit(output_node)
    ancestors = visited.copy()
    for node_id in graph:
        visit(node_id)
    if not any("minimax_h3" in info[graph[n]["class_type"]].get("python_module", "") for n in ancestors):
        raise ValueError("Saver has no local H3 node in its dependency chain")
    return ancestors


def bind(graph, plan, info):
    output_node = str(plan["output_node"])
    ancestors = validate_graph(graph, info, output_node)
    result = deepcopy(graph)
    seen = set()
    if not isinstance(plan.get("bindings"), list) or not plan["bindings"]:
        raise ValueError("Provide at least one explicit binding")
    for binding in plan["bindings"]:
        node_id, key = str(binding["node"]), binding["input"]
        if (node_id, key) in seen:
            raise ValueError(f"Duplicate binding: {node_id}.{key}")
        seen.add((node_id, key))
        if node_id not in ancestors or key not in result[node_id]["inputs"]:
            raise ValueError(f"Binding does not target an existing input used by the saver: {node_id}.{key}")
        old = result[node_id]["inputs"][key]
        if isinstance(old, (dict, list)) or isinstance(binding["value"], (dict, list)):
            raise ValueError("Bind scalar inputs only; do not replace connections or dynamic groups")
        if "expected" not in binding or old != binding["expected"] or type(old) is not type(binding["expected"]):
            raise ValueError(f"Stale template at {node_id}.{key}: expected old value did not match")
        result[node_id]["inputs"][key] = binding["value"]
    validate_graph(result, info, output_node)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("workflow", "bindings", "object-info", "out"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Output already exists; choose a new versioned filename")
    graph = read_json(args.workflow)
    plan = read_json(args.bindings)
    info = read_json(args.object_info)
    result = bind(graph, plan, info)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.out.resolve()), "graph_sha256": digest(result),
                      "output_node": plan["output_node"], "submitted": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
