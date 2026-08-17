import { useMemo, useState } from "react";
import type { GraphData } from "../api/types";
import EmptyState from "./EmptyState";

const TYPE_COLORS: Record<string, string> = {
  Person: "#818cf8",
  Organization: "#22d3ee",
  Paper: "#34d399",
  Model: "#fbbf24",
  Dataset: "#fb923c",
  Technology: "#a78bfa",
  Product: "#f472b6",
  Concept: "#94a3b8",
  Metric: "#38bdf8",
};

function colorFor(type: string): string {
  return TYPE_COLORS[type] ?? "#9aa3b5";
}

export default function GraphView({ data }: { data: GraphData }) {
  const [selected, setSelected] = useState<string | null>(null);

  const layout = useMemo(() => {
    const width = 640;
    const height = 420;
    const cx = width / 2;
    const cy = height / 2;
    const types = Array.from(new Set(data.nodes.map((n) => n.type)));
    const byType = new Map<string, typeof data.nodes>();
    for (const node of data.nodes) {
      const list = byType.get(node.type) ?? [];
      list.push(node);
      byType.set(node.type, list);
    }
    const positions = new Map<string, { x: number; y: number }>();
    types.forEach((type, ring) => {
      const nodes = byType.get(type) ?? [];
      const radius = 70 + ring * 70;
      nodes.forEach((node, index) => {
        const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2 - Math.PI / 2;
        positions.set(node.id, {
          x: cx + Math.cos(angle) * radius,
          y: cy + Math.sin(angle) * radius,
        });
      });
    });
    return { width, height, positions };
  }, [data]);

  if (!data.nodes.length) {
    return (
      <EmptyState icon="🕸️" title="No graph yet">
        <p>Enable graph mode on the collection and extract entities from a document.</p>
      </EmptyState>
    );
  }

  const selectedNode = data.nodes.find((n) => n.id === selected);
  const neighbors = selected
    ? data.edges.filter((e) => e.source === selected || e.target === selected)
    : [];

  return (
    <div>
      <svg
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        className="graph-canvas"
        role="img"
        aria-label="Knowledge graph"
      >
        {data.edges.map((edge) => {
          const a = layout.positions.get(edge.source);
          const b = layout.positions.get(edge.target);
          if (!a || !b) return null;
          const active = selected && (edge.source === selected || edge.target === selected);
          return (
            <g key={edge.id}>
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={active ? "var(--accent-strong)" : "var(--border-strong)"}
                strokeWidth={active ? 1.8 : 1}
              />
            </g>
          );
        })}
        {data.nodes.map((node) => {
          const pos = layout.positions.get(node.id);
          if (!pos) return null;
          const active = selected === node.id;
          return (
            <g
              key={node.id}
              transform={`translate(${pos.x}, ${pos.y})`}
              style={{ cursor: "pointer" }}
              onClick={() => setSelected(node.id === selected ? null : node.id)}
            >
              <circle
                r={active ? 11 : 8}
                fill={colorFor(node.type)}
                stroke={active ? "white" : "transparent"}
                strokeWidth={1.5}
              />
              <text y={20} textAnchor="middle" fill="var(--text-dim)" fontSize="10">
                {node.name.length > 18 ? `${node.name.slice(0, 16)}…` : node.name}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="row wrap" style={{ marginTop: 10, gap: 8 }}>
        {Object.entries(TYPE_COLORS).map(([type, color]) => (
          <span key={type} className="badge" style={{ borderColor: color, color }}>
            {type}
          </span>
        ))}
      </div>
      {selectedNode && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="row spread">
            <strong>{selectedNode.name}</strong>
            <span className="badge">{selectedNode.type}</span>
          </div>
          {selectedNode.description && (
            <p className="dim" style={{ marginTop: 8, fontSize: 13 }}>
              {selectedNode.description}
            </p>
          )}
          {neighbors.length > 0 && (
            <div style={{ marginTop: 10 }}>
              {neighbors.map((edge) => {
                const otherId = edge.source === selectedNode.id ? edge.target : edge.source;
                const other = data.nodes.find((n) => n.id === otherId);
                return (
                  <div key={edge.id} className="dim" style={{ fontSize: 12.5, padding: "3px 0" }}>
                    {edge.relation} → {other?.name ?? otherId}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
