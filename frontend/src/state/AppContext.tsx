import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api } from "../api/client";
import type { AppConfig, Collection, Provider } from "../api/types";

interface Toast {
  id: number;
  kind: "info" | "error" | "success";
  text: string;
}

interface AppState {
  config: AppConfig | null;
  providers: Provider[];
  collections: Collection[];
  refreshCollections: () => Promise<void>;
  refreshProviders: () => Promise<void>;
  toast: (text: string, kind?: Toast["kind"]) => void;
  backendDown: boolean;
}

const Ctx = createContext<AppState>(null!);

export function useApp(): AppState {
  return useContext(Ctx);
}

let toastId = 0;

export function AppProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [backendDown, setBackendDown] = useState(false);

  const toast = useCallback((text: string, kind: Toast["kind"] = "info") => {
    const id = ++toastId;
    setToasts((prev) => [...prev, { id, kind, text }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4500);
  }, []);

  const refreshCollections = useCallback(async () => {
    try {
      setCollections(await api.listCollections());
    } catch {
      /* surfaced through backendDown */
    }
  }, []);

  const refreshProviders = useCallback(async () => {
    try {
      setProviders(await api.providers());
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [cfg, prov, cols] = await Promise.all([
          api.config(),
          api.providers(),
          api.listCollections(),
        ]);
        setConfig(cfg);
        setProviders(prov);
        setCollections(cols);
        setBackendDown(false);
      } catch {
        setBackendDown(true);
      }
    })();
  }, []);

  const value = useMemo(
    () => ({
      config,
      providers,
      collections,
      refreshCollections,
      refreshProviders,
      toast,
      backendDown,
    }),
    [config, providers, collections, refreshCollections, refreshProviders, toast, backendDown],
  );

  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="toast-stack">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            {t.text}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
