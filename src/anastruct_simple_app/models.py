from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NodeSpec:
    name: str
    x: float
    y: float
    role: str = "structural"


@dataclass(slots=True)
class ElementSpec:
    name: str
    start: str
    end: str
    e: float
    a: float
    i: float

    @property
    def ea(self) -> float:
        return self.e * self.a

    @property
    def ei(self) -> float:
        return self.e * self.i


@dataclass(slots=True)
class SupportSpec:
    node: str
    kind: str


@dataclass(slots=True)
class NodeLoadSpec:
    node: str
    fx: float = 0.0
    fy: float = 0.0
    moment: float = 0.0


@dataclass(slots=True)
class DistributedLoadSpec:
    q: float
    element: str | None = None
    direction: str = "element"
    start_node: str | None = None
    end_node: str | None = None


@dataclass(slots=True)
class StructureModel:
    nodes: list[NodeSpec] = field(default_factory=list)
    elements: list[ElementSpec] = field(default_factory=list)
    supports: list[SupportSpec] = field(default_factory=list)
    node_loads: list[NodeLoadSpec] = field(default_factory=list)
    distributed_loads: list[DistributedLoadSpec] = field(default_factory=list)


@dataclass(slots=True)
class NodeResult:
    name: str
    node_id: int
    ux: float
    uy: float
    phi: float
    rx: float
    ry: float
    rm: float


@dataclass(slots=True)
class ElementResult:
    name: str
    element_id: int
    length: float
    alpha: float
    n_min: float
    n_max: float
    q_min: float
    q_max: float
    m_min: float
    m_max: float
    u_min: float
    u_max: float
    w_min: float | None = None
    w_max: float | None = None


@dataclass(slots=True)
class ResultSummary:
    max_displacement: float
    max_axial: float
    max_shear: float
    max_moment: float


@dataclass(slots=True)
class SolveResult:
    summary: ResultSummary
    node_results: list[NodeResult]
    element_results: list[ElementResult]
    system: Any
    node_id_map: dict[str, int]
    element_id_map: dict[str, int]
