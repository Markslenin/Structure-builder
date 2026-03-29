from __future__ import annotations

from .models import (
    DistributedLoadSpec,
    ElementSpec,
    NodeLoadSpec,
    NodeSpec,
    StructureModel,
    SupportSpec,
)

SUPPORT_ALIASES = {
    "fixed": "fixed",
    "hinged": "hinged",
    "pinned": "hinged",
    "roller_x": "roller_x",
    "rollerx": "roller_x",
    "roller_y": "roller_y",
    "rollery": "roller_y",
}

LOAD_DIRECTIONS = {"element", "parallel", "x", "y"}
NODE_ROLES = {"structural", "reference", "hinge"}


class ParseError(ValueError):
    """Raised when user input cannot be parsed."""


def parse_model_from_text(
    *,
    nodes_text: str,
    elements_text: str,
    supports_text: str,
    node_loads_text: str,
    distributed_loads_text: str,
) -> StructureModel:
    model = StructureModel(
        nodes=_parse_nodes(nodes_text),
        elements=_parse_elements(elements_text),
        supports=_parse_supports(supports_text),
        node_loads=_parse_node_loads(node_loads_text),
        distributed_loads=_parse_distributed_loads(distributed_loads_text),
    )
    _validate_model(model)
    return model


def model_to_text_sections(model: StructureModel) -> dict[str, str]:
    return {
        "nodes": "\n".join(f"{row.name},{row.x},{row.y},{row.role}" for row in model.nodes),
        "elements": "\n".join(
            f"{row.name},{row.start},{row.end},{row.e},{row.a},{row.i}" for row in model.elements
        ),
        "supports": "\n".join(f"{row.node},{row.kind}" for row in model.supports),
        "node_loads": "\n".join(f"{row.node},{row.fx},{row.fy},{row.moment}" for row in model.node_loads),
        "distributed_loads": "\n".join(
            f"{row.element},{row.q},{row.direction}"
            if row.element is not None
            else f"{row.start_node},{row.end_node},{row.q},{row.direction}"
            for row in model.distributed_loads
        ),
    }


def _parse_nodes(text: str) -> list[NodeSpec]:
    rows: list[NodeSpec] = []
    seen: set[str] = set()
    for line_no, parts in _iter_parts(text):
        if len(parts) not in {3, 4}:
            raise ParseError(f"Line {line_no}: node should have 3 or 4 columns.")
        name = parts[0]
        if name in seen:
            raise ParseError(f"Line {line_no}: duplicate node name {name}.")
        seen.add(name)
        role = "structural" if len(parts) == 3 else parts[3].strip().lower()
        if role not in NODE_ROLES:
            allowed = ", ".join(sorted(NODE_ROLES))
            raise ParseError(f"Line {line_no}: invalid node role {role}. Allowed: {allowed}.")
        rows.append(NodeSpec(name=name, x=_to_float(parts[1], line_no), y=_to_float(parts[2], line_no), role=role))
    return rows


def _parse_elements(text: str) -> list[ElementSpec]:
    rows: list[ElementSpec] = []
    seen: set[str] = set()
    for line_no, parts in _iter_parts(text):
        _expect_columns(parts, 6, line_no, "element")
        name = parts[0]
        if name in seen:
            raise ParseError(f"Line {line_no}: duplicate element name {name}.")
        seen.add(name)
        element = ElementSpec(
            name=name,
            start=parts[1],
            end=parts[2],
            e=_to_float(parts[3], line_no),
            a=_to_float(parts[4], line_no),
            i=_to_float(parts[5], line_no),
        )
        if element.start == element.end:
            raise ParseError(f"Line {line_no}: element {name} start and end cannot be the same.")
        if element.e <= 0 or element.a <= 0 or element.i <= 0:
            raise ParseError(f"Line {line_no}: element {name} requires positive E, A, I.")
        rows.append(element)
    return rows


def _parse_supports(text: str) -> list[SupportSpec]:
    rows: list[SupportSpec] = []
    for line_no, parts in _iter_parts(text):
        _expect_columns(parts, 2, line_no, "support")
        kind = SUPPORT_ALIASES.get(parts[1].strip().lower())
        if kind is None:
            allowed = ", ".join(sorted(set(SUPPORT_ALIASES.values())))
            raise ParseError(f"Line {line_no}: invalid support type {parts[1]}. Allowed: {allowed}.")
        rows.append(SupportSpec(node=parts[0], kind=kind))
    return rows


def _parse_node_loads(text: str) -> list[NodeLoadSpec]:
    rows: list[NodeLoadSpec] = []
    for line_no, parts in _iter_parts(text):
        _expect_columns(parts, 4, line_no, "node load")
        rows.append(
            NodeLoadSpec(
                node=parts[0],
                fx=_to_float(parts[1], line_no),
                fy=_to_float(parts[2], line_no),
                moment=_to_float(parts[3], line_no),
            )
        )
    return rows


def _parse_distributed_loads(text: str) -> list[DistributedLoadSpec]:
    rows: list[DistributedLoadSpec] = []
    for line_no, parts in _iter_parts(text):
        if len(parts) not in {3, 4}:
            raise ParseError(f"Line {line_no}: distributed load should have 3 or 4 columns.")
        direction = parts[-1].strip().lower()
        if direction not in LOAD_DIRECTIONS:
            allowed = ", ".join(sorted(LOAD_DIRECTIONS))
            raise ParseError(f"Line {line_no}: invalid distributed load direction {direction}. Allowed: {allowed}.")
        if len(parts) == 3:
            rows.append(DistributedLoadSpec(element=parts[0], q=_to_float(parts[1], line_no), direction=direction))
        else:
            rows.append(
                DistributedLoadSpec(
                    start_node=parts[0],
                    end_node=parts[1],
                    q=_to_float(parts[2], line_no),
                    direction=direction,
                )
            )
    return rows


def _validate_model(model: StructureModel) -> None:
    if len(model.nodes) < 2:
        raise ParseError("At least 2 nodes are required.")
    if not model.elements:
        raise ParseError("At least 1 element is required.")

    node_names = {item.name for item in model.nodes}
    element_names = {item.name for item in model.elements}
    node_coordinates: dict[tuple[float, float], str] = {}
    used_nodes: set[str] = set()

    for node in model.nodes:
        coordinate = (node.x, node.y)
        if coordinate in node_coordinates:
            other = node_coordinates[coordinate]
            raise ParseError(f"Node {node.name} duplicates coordinates of {other}.")
        node_coordinates[coordinate] = node.name

    for element in model.elements:
        if element.start not in node_names or element.end not in node_names:
            raise ParseError(f"Element {element.name} references a missing node.")
        used_nodes.add(element.start)
        used_nodes.add(element.end)

    dangling = [node.name for node in model.nodes if node.name not in used_nodes]
    if dangling:
        raise ParseError(f"These nodes are not connected to any element: {', '.join(dangling)}")

    for support in model.supports:
        if support.node not in node_names:
            raise ParseError(f"Support references missing node: {support.node}")

    for load in model.node_loads:
        if load.node not in node_names:
            raise ParseError(f"Node load references missing node: {load.node}")

    for load in model.distributed_loads:
        if load.element is not None:
            if load.element not in element_names:
                raise ParseError(f"Distributed load references missing element: {load.element}")
        else:
            if load.start_node not in node_names or load.end_node not in node_names:
                raise ParseError("Distributed load references missing start/end node.")


def _iter_parts(text: str):
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        yield line_no, [part.strip() for part in line.split(",")]


def _expect_columns(parts: list[str], expected: int, line_no: int, label: str) -> None:
    if len(parts) != expected:
        raise ParseError(f"Line {line_no}: {label} should have {expected} columns, got {len(parts)}.")


def _to_float(value: str, line_no: int) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ParseError(f"Line {line_no}: cannot parse numeric value {value}.") from exc
