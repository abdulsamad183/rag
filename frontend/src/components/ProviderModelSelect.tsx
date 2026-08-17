import type { Provider } from "../api/types";

export default function ProviderModelSelect({
  providers,
  provider,
  model,
  onProvider,
  onModel,
  compact,
  disabled,
}: {
  providers: Provider[];
  provider: string;
  model: string;
  onProvider: (name: string) => void;
  onModel: (name: string) => void;
  compact?: boolean;
  disabled?: boolean;
}) {
  const current = providers.find((p) => p.name === provider);
  const models = current?.models ?? [];
  const klass = compact ? "mini-select" : "select";

  return (
    <>
      <select
        className={klass}
        value={provider}
        disabled={disabled}
        title={current?.note || current?.label}
        onChange={(event) => {
          const next = event.target.value;
          const nextProvider = providers.find((p) => p.name === next);
          onProvider(next);
          onModel(nextProvider?.default_model || nextProvider?.models[0]?.name || "");
        }}
      >
        {providers.map((item) => (
          <option key={item.name} value={item.name} disabled={!item.configured}>
            {item.label}
            {!item.configured ? " (not configured)" : ""}
          </option>
        ))}
      </select>
      <select
        className={klass}
        value={model}
        disabled={disabled || !models.length}
        onChange={(event) => onModel(event.target.value)}
      >
        {models.map((item) => (
          <option key={item.name} value={item.name}>
            {item.label}
            {item.installed === false ? " (not pulled)" : ""}
          </option>
        ))}
      </select>
    </>
  );
}
