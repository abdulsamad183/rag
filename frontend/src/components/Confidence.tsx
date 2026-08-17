import type { Confidence } from "../api/types";

const LEVEL_COLORS: Record<string, string> = {
  high: "var(--green)",
  medium: "var(--yellow)",
  low: "#fb923c",
  insufficient: "var(--red)",
};

const SIGNAL_LABELS: Record<string, string> = {
  retrieval: "Retrieval",
  rerank: "Rerank",
  coverage: "Coverage",
  claim_support: "Claim support",
  contradiction: "Consistency",
  source_trust: "Source trust",
};

export function ConfidenceRing({ confidence }: { confidence: Confidence }) {
  const radius = 23;
  const circumference = 2 * Math.PI * radius;
  const fraction = Math.max(0, Math.min(1, confidence.score));
  const color = LEVEL_COLORS[confidence.level] ?? "var(--accent)";
  return (
    <div className="confidence-ring" title={`Confidence: ${confidence.level}`}>
      <svg width="54" height="54">
        <circle cx="27" cy="27" r={radius} fill="none" stroke="var(--border)" strokeWidth="5" />
        <circle
          cx="27"
          cy="27"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - fraction)}
        />
      </svg>
      <div className="value" style={{ color }}>
        {Math.round(confidence.score * 100)}
      </div>
    </div>
  );
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const klass =
    confidence.level === "high" ? "green" : confidence.level === "medium" ? "yellow" : "red";
  return (
    <span className={`badge ${klass}`}>
      {Math.round(confidence.score * 100)}% · {confidence.level}
    </span>
  );
}

export function ConfidenceSignals({ confidence }: { confidence: Confidence }) {
  const entries = Object.entries(confidence.signals);
  if (!entries.length) return null;
  return (
    <div>
      {entries.map(([name, value]) => (
        <div key={name} className="signal-row">
          <span className="name">{SIGNAL_LABELS[name] ?? name}</span>
          <div className="score-bar">
            <div style={{ width: `${Math.min(100, value * 100)}%` }} />
          </div>
          <span className="num">{value.toFixed(2)}</span>
        </div>
      ))}
    </div>
  );
}
