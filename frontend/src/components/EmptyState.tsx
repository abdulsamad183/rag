import type { ReactNode } from "react";

export default function EmptyState({
  icon,
  title,
  children,
}: {
  icon: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="icon">{icon}</div>
      <h3>{title}</h3>
      {children}
    </div>
  );
}
