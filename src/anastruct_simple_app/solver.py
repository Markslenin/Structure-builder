from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from math import hypot
from typing import Any

from .models import ElementResult, ElementSpec, NodeResult, NodeSpec, ResultSummary, SolveResult, StructureModel

try:
    from anastruct import SystemElements
except Exception:  # pragma: no cover
    SystemElements = None


PLOT_METHODS = {
    "structure": "show_structure",
    "reaction": "show_reaction_force",
    "displacement": "show_displacement",
    "axial": "show_axial_force",
    "shear": "show_shear_force",
    "moment": "show_bending_moment",
    "all": "show_results",
}

PLOTTER_METHODS = {
    "structure": "plot_structure",
    "reaction": "reaction_force",
    "displacement": "displacements",
    "axial": "axial_force",
    "shear": "shear_force",
    "moment": "bending_moment",
    "all": "results_plot",
}


class SolveError(RuntimeError):
    """Raised when the structure cannot be solved."""


def solve_structure(model: StructureModel, *, mesh: int = 80) -> SolveResult:
    if SystemElements is None:
        raise SolveError("anastruct is not available in the current Python environment.")

    system = SystemElements(mesh=mesh)
    node_lookup = {node.name: node for node in model.nodes}
    node_id_map: dict[str, int] = {}
    element_segment_map: dict[str, list[int]] = {}

    try:
        for element in model.elements:
            segment_ids = _add_element_with_internal_nodes(system, model, node_lookup, node_id_map, element)
            element_segment_map[element.name] = segment_ids

        for support in model.supports:
            node_id = _require_mapping(node_id_map, support.node, "node")
            if support.kind == "fixed":
                system.add_support_fixed(node_id=node_id)
            elif support.kind == "hinged":
                system.add_support_hinged(node_id=node_id)
            elif support.kind == "roller_x":
                system.add_support_roll(node_id=node_id, direction="x")
            elif support.kind == "roller_y":
                system.add_support_roll(node_id=node_id, direction="y")
            else:
                raise SolveError(f"Unsupported support type: {support.kind}")

        for load in model.node_loads:
            node_id = _require_mapping(node_id_map, load.node, "node")
            if abs(load.fx) > 0 or abs(load.fy) > 0:
                system.point_load(node_id=node_id, Fx=load.fx, Fy=load.fy)
            if abs(load.moment) > 0:
                system.moment_load(node_id=node_id, Ty=load.moment)

        for load in model.distributed_loads:
            for element_id in _resolve_distributed_load_element_ids(model, element_segment_map, load):
                system.q_load(q=load.q, element_id=element_id, direction=load.direction)

        system.solve()
    except Exception as exc:
        raise SolveError(f"Failed to solve structure: {exc}") from exc

    node_result_rows = _index_rows(system.get_node_results_system())
    node_disp_rows = _index_rows(system.get_node_displacements())
    element_result_rows = _index_rows(system.get_element_results(verbose=False))

    node_results: list[NodeResult] = []
    for node in model.nodes:
        node_id = node_id_map.get(node.name)
        if node_id is None:
            continue
        system_row = _require_row(node_result_rows, node_id, "node result")
        disp_row = _require_row(node_disp_rows, node_id, "node displacement")
        node_results.append(
            NodeResult(
                name=node.name,
                node_id=node_id,
                rx=_get_number(system_row, "Fx", 1),
                ry=_get_number(system_row, "Fy", 2),
                rm=_get_number(system_row, ("Tz", "Ty"), 3),
                ux=_get_number(disp_row, "ux", 1),
                uy=_get_number(disp_row, "uy", 2),
                phi=_get_number(disp_row, ("phi_z", "phi_y", "phi"), 3),
            )
        )

    element_results: list[ElementResult] = []
    for element in model.elements:
        segment_ids = element_segment_map.get(element.name)
        if not segment_ids:
            continue
        rows = [_require_row(element_result_rows, element_id, "element result") for element_id in segment_ids]
        element_results.append(_aggregate_element_result(element, segment_ids, rows))

    summary = ResultSummary(
        max_displacement=max((hypot(row.ux, row.uy) for row in node_results), default=0.0),
        max_axial=max((max(abs(row.n_min), abs(row.n_max)) for row in element_results), default=0.0),
        max_shear=max((max(abs(row.q_min), abs(row.q_max)) for row in element_results), default=0.0),
        max_moment=max((max(abs(row.m_min), abs(row.m_max)) for row in element_results), default=0.0),
    )

    return SolveResult(
        summary=summary,
        node_results=node_results,
        element_results=element_results,
        system=system,
        node_id_map=node_id_map,
        element_id_map={name: ids[0] for name, ids in element_segment_map.items() if ids},
    )


def _resolve_distributed_load_element_ids(
    model: StructureModel,
    element_segment_map: dict[str, list[int]],
    load: Any,
) -> list[int]:
    if load.element is not None:
        return _require_segment_mapping(element_segment_map, load.element)

    if load.start_node is None or load.end_node is None:
        raise SolveError("Distributed load must reference an element or a node span.")

    same_element_ids = _resolve_same_element_node_span(model, element_segment_map, load.start_node, load.end_node)
    if same_element_ids is not None:
        return same_element_ids

    path = _find_node_path(model, load.start_node, load.end_node)
    if len(path) < 2:
        raise SolveError("Invalid node span for distributed load.")

    for node_name in path[1:-1]:
        node = next(item for item in model.nodes if item.name == node_name)
        if node.role != "reference":
            raise SolveError(
                f"Node-span distributed load can only pass through reference nodes. "
                f"Node {node_name} is {node.role}."
            )

    element_ids: list[int] = []
    for start_name, end_name in zip(path, path[1:]):
        element = _find_element_between(model, start_name, end_name)
        if element is None:
            raise SolveError(f"No element found between {start_name} and {end_name}.")
        element_ids.extend(_require_segment_mapping(element_segment_map, element.name))
    return element_ids


def _resolve_same_element_node_span(
    model: StructureModel,
    element_segment_map: dict[str, list[int]],
    start_node: str,
    end_node: str,
) -> list[int] | None:
    if start_node == end_node:
        raise SolveError("Distributed load start node and end node must be different.")

    node_lookup = {node.name: node for node in model.nodes}
    for element in model.elements:
        start = node_lookup[element.start]
        end = node_lookup[element.end]
        chain_nodes = [start, *_find_internal_nodes_on_element(model, element, start, end), end]
        names = [node.name for node in chain_nodes]
        if start_node not in names or end_node not in names:
            continue

        start_index = names.index(start_node)
        end_index = names.index(end_node)
        if start_index == end_index:
            raise SolveError("Distributed load start node and end node must be different.")

        low = min(start_index, end_index)
        high = max(start_index, end_index)
        segment_ids = _require_segment_mapping(element_segment_map, element.name)
        return segment_ids[low:high]
    return None


def _add_element_with_internal_nodes(
    system: Any,
    model: StructureModel,
    node_lookup: dict[str, NodeSpec],
    node_id_map: dict[str, int],
    element: ElementSpec,
) -> list[int]:
    start = node_lookup[element.start]
    end = node_lookup[element.end]
    internal_nodes = _find_internal_nodes_on_element(model, element, start, end)
    chain = [start, *internal_nodes, end]

    segment_ids: list[int] = []
    for left, right in zip(chain, chain[1:]):
        ana_element_id = system.add_element(
            location=[[left.x, left.y], [right.x, right.y]],
            EA=element.ea,
            EI=element.ei,
        )
        ana_element = system.element_map[ana_element_id]
        _bind_node_id(node_id_map, left.name, ana_element.node_id1)
        _bind_node_id(node_id_map, right.name, ana_element.node_id2)
        segment_ids.append(ana_element_id)
    return segment_ids


def _find_internal_nodes_on_element(
    model: StructureModel,
    element: ElementSpec,
    start: NodeSpec,
    end: NodeSpec,
) -> list[NodeSpec]:
    items: list[tuple[float, NodeSpec]] = []
    for node in model.nodes:
        if node.name in {element.start, element.end}:
            continue
        factor = _point_factor_on_segment(node, start, end)
        if factor is None:
            continue
        items.append((factor, node))
    items.sort(key=lambda item: item[0])
    return [node for _, node in items]


def _point_factor_on_segment(node: NodeSpec, start: NodeSpec, end: NodeSpec, tolerance: float = 1e-9) -> float | None:
    dx = end.x - start.x
    dy = end.y - start.y
    cross = (node.x - start.x) * dy - (node.y - start.y) * dx
    if abs(cross) > tolerance:
        return None
    length_sq = dx * dx + dy * dy
    if length_sq <= tolerance:
        return None
    dot = (node.x - start.x) * dx + (node.y - start.y) * dy
    factor = dot / length_sq
    if factor <= tolerance or factor >= 1.0 - tolerance:
        return None
    return factor


def _aggregate_element_result(element: ElementSpec, segment_ids: list[int], rows: list[Any]) -> ElementResult:
    lengths = [_get_number(row, "length") for row in rows]
    alphas = [_get_number(row, "alpha") for row in rows]
    n_mins = [_get_number(row, "Nmin") for row in rows]
    n_maxs = [_get_number(row, "Nmax") for row in rows]
    q_mins = [_get_number(row, "Qmin", default=0.0) for row in rows]
    q_maxs = [_get_number(row, "Qmax", default=0.0) for row in rows]
    m_mins = [_get_number(row, "Mmin", default=0.0) for row in rows]
    m_maxs = [_get_number(row, "Mmax", default=0.0) for row in rows]
    u_mins = [_get_number(row, "umin") for row in rows]
    u_maxs = [_get_number(row, "umax") for row in rows]
    w_values = [_get_optional_number(row, "wmin") for row in rows] + [_get_optional_number(row, "wmax") for row in rows]
    w_values = [value for value in w_values if value is not None]

    return ElementResult(
        name=element.name,
        element_id=segment_ids[0],
        length=sum(lengths),
        alpha=alphas[0],
        n_min=min(n_mins),
        n_max=max(n_maxs),
        q_min=min(q_mins),
        q_max=max(q_maxs),
        m_min=min(m_mins),
        m_max=max(m_maxs),
        u_min=min(u_mins),
        u_max=max(u_maxs),
        w_min=min(w_values) if w_values else None,
        w_max=max(w_values) if w_values else None,
    )


def _find_node_path(model: StructureModel, start: str, end: str) -> list[str]:
    adjacency: dict[str, list[str]] = {}
    for element in model.elements:
        adjacency.setdefault(element.start, []).append(element.end)
        adjacency.setdefault(element.end, []).append(element.start)

    queue: deque[str] = deque([start])
    parent: dict[str, str | None] = {start: None}
    while queue:
        current = queue.popleft()
        if current == end:
            break
        for neighbor in adjacency.get(current, []):
            if neighbor not in parent:
                parent[neighbor] = current
                queue.append(neighbor)

    if end not in parent:
        raise SolveError(f"No connected path found between {start} and {end}.")

    path: list[str] = []
    cursor: str | None = end
    while cursor is not None:
        path.append(cursor)
        cursor = parent[cursor]
    path.reverse()
    return path


def _find_element_between(model: StructureModel, start: str, end: str):
    for element in model.elements:
        if {element.start, element.end} == {start, end}:
            return element
    return None


def open_result_plot(result: SolveResult, kind: str) -> None:
    method_name = PLOT_METHODS.get(kind)
    if method_name is None:
        raise SolveError(f"Unsupported plot kind: {kind}")
    if not can_plot(result, kind):
        raise SolveError("matplotlib plotting backend is not available.")
    method = getattr(result.system, method_name, None)
    if method is None:
        raise SolveError(f"anaStruct plot method not found: {method_name}")
    method()


def can_plot(result: SolveResult, kind: str) -> bool:
    plotter_method = PLOTTER_METHODS.get(kind)
    if plotter_method is None:
        return False
    plotter = getattr(result.system, "plotter", None)
    return plotter is not None and hasattr(plotter, plotter_method)


def available_plot_kinds(result: SolveResult) -> set[str]:
    return {kind for kind in PLOT_METHODS if can_plot(result, kind)}


def _index_rows(rows: Any) -> dict[int, Any]:
    items = _normalize_rows(rows)
    indexed: dict[int, Any] = {}
    for row in items:
        indexed[_get_row_id(row)] = row
    return indexed


def _normalize_rows(rows: Any) -> list[Any]:
    if rows is None:
        return []
    if isinstance(rows, Mapping):
        if "id" in rows:
            return [rows]
        return list(rows.values())
    if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes, bytearray)):
        return list(rows)
    if isinstance(rows, Iterable):
        return list(rows)
    return [rows]


def _get_row_id(row: Any) -> int:
    if isinstance(row, Mapping):
        if "id" not in row:
            raise SolveError(f"Result row missing id field: {row}")
        return int(row["id"])
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray)):
        if not row:
            raise SolveError("Result row sequence is empty.")
        return int(row[0])
    raise SolveError(f"Unsupported result row type: {type(row).__name__}")


def _require_row(rows: dict[int, Any], row_id: int, label: str) -> Any:
    try:
        return rows[row_id]
    except KeyError as exc:
        raise SolveError(f"Missing {label} for id={row_id}.") from exc


def _get_number(
    row: Any,
    keys: str | tuple[str, ...],
    tuple_index: int | None = None,
    *,
    default: float | None = None,
) -> float:
    if isinstance(row, Mapping):
        key_list = (keys,) if isinstance(keys, str) else keys
        for key in key_list:
            if key in row and row[key] is not None:
                return float(row[key])
        if default is not None:
            return float(default)
        raise SolveError(f"Missing result field: {keys}")
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray)):
        if tuple_index is None:
            raise SolveError("Tuple-like result requires an index.")
        if tuple_index < len(row):
            return float(row[tuple_index])
        if default is not None:
            return float(default)
        raise SolveError(f"Result row too short for index {tuple_index}.")
    if default is not None:
        return float(default)
    raise SolveError(f"Cannot read numeric value from row: {row}")


def _get_optional_number(row: Any, key: str) -> float | None:
    if isinstance(row, Mapping):
        value = row.get(key)
        return None if value is None else float(value)
    return None


def _bind_node_id(mapping: dict[str, int], label: str, node_id: int) -> None:
    existing = mapping.get(label)
    if existing is not None and existing != node_id:
        raise SolveError(f"Node {label} maps to multiple anaStruct node ids.")
    mapping[label] = node_id


def _require_mapping(mapping: dict[str, int], label: str, kind: str) -> int:
    try:
        return mapping[label]
    except KeyError as exc:
        raise SolveError(f"{kind} {label} was not mapped into anaStruct.") from exc


def _require_segment_mapping(mapping: dict[str, list[int]], label: str) -> list[int]:
    try:
        segment_ids = mapping[label]
    except KeyError as exc:
        raise SolveError(f"element {label} was not mapped into anaStruct.") from exc
    if not segment_ids:
        raise SolveError(f"element {label} has no anaStruct segments.")
    return segment_ids
