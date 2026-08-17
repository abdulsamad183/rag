import { Fragment, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Replace [n] citation markers inside rendered text nodes with clickable chips. */
function withCitationChips(children: ReactNode, onCite?: (marker: number) => void): ReactNode {
  if (!onCite) return children;

  const transform = (node: ReactNode, key?: string | number): ReactNode => {
    if (typeof node === "string") {
      const parts = node.split(/(\[\d+\])/g);
      if (parts.length === 1) return node;
      return (
        <Fragment key={key}>
          {parts.map((part, index) => {
            const match = /^\[(\d+)\]$/.exec(part);
            if (match) {
              const marker = Number(match[1]);
              return (
                <button
                  key={index}
                  className="citation-chip"
                  title={`Show evidence [${marker}]`}
                  onClick={() => onCite(marker)}
                >
                  {marker}
                </button>
              );
            }
            return part;
          })}
        </Fragment>
      );
    }
    if (Array.isArray(node)) return node.map((child, index) => transform(child, index));
    return node;
  };

  return transform(children);
}

export default function Markdown({
  text,
  onCite,
}: {
  text: string;
  onCite?: (marker: number) => void;
}) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p>{withCitationChips(children, onCite)}</p>,
          li: ({ children }) => <li>{withCitationChips(children, onCite)}</li>,
          td: ({ children }) => <td>{withCitationChips(children, onCite)}</td>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
