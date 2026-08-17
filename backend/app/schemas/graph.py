from __future__ import annotations

from pydantic import BaseModel


class GraphNode(BaseModel):
    id: str
    name: str
    type: str
    description: str = ""


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: str
    weight: float = 1.0


class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
