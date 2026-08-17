import type { ReactNode } from "react";

export default function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="modal">
        <div className="row spread" style={{ marginBottom: 14 }}>
          <h2 style={{ margin: 0 }}>{title}</h2>
          <button className="btn ghost small" onClick={onClose}>
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
