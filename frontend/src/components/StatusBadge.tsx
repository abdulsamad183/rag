import { ingestLabel, statusClass } from "../utils/format";

export default function StatusBadge({ status }: { status: string }) {
  return <span className={`badge ${statusClass(status)}`}>{ingestLabel(status)}</span>;
}
