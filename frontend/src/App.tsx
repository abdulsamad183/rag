import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import ErrorBoundary from "./components/ErrorBoundary";
import { useApp } from "./state/AppContext";
import ChatPage from "./pages/ChatPage";
import CollectionsPage from "./pages/CollectionsPage";
import CollectionDetailPage from "./pages/CollectionDetailPage";
import DashboardPage from "./pages/DashboardPage";
import EvaluationPage from "./pages/EvaluationPage";
import RunDetailPage from "./pages/RunDetailPage";
import SettingsPage from "./pages/SettingsPage";
import TraceDetailPage from "./pages/TraceDetailPage";
import TracesPage from "./pages/TracesPage";

export default function App() {
  const { backendDown, config } = useApp();

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="logo">◈</div>
          Adaptive RAG
        </div>

        <NavLink to="/" end className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
          <span className="icon">⌂</span> Dashboard
        </NavLink>
        <NavLink to="/chat" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
          <span className="icon">💬</span> Chat
        </NavLink>
        <NavLink to="/collections" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
          <span className="icon">🗂</span> Collections
        </NavLink>

        <div className="section-label">Observe</div>
        <NavLink to="/traces" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
          <span className="icon">🔍</span> Traces
        </NavLink>
        <NavLink to="/evaluation" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
          <span className="icon">📊</span> Evaluation
        </NavLink>

        <div className="section-label">System</div>
        <NavLink to="/settings" className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
          <span className="icon">⚙️</span> Settings
        </NavLink>

        <div className="sidebar-footer">
          {backendDown ? (
            <span style={{ color: "var(--red)" }}>● Backend unreachable</span>
          ) : (
            <span style={{ color: "var(--green)" }}>● Connected</span>
          )}
          {config?.local_mode && <span className="badge yellow">LOCAL MODE</span>}
        </div>
      </aside>

      <main className="main">
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/chat/:conversationId" element={<ChatPage />} />
            <Route path="/collections" element={<CollectionsPage />} />
            <Route path="/collections/:collectionId" element={<CollectionDetailPage />} />
            <Route path="/traces" element={<TracesPage />} />
            <Route path="/traces/:traceId" element={<TraceDetailPage />} />
            <Route path="/evaluation" element={<EvaluationPage />} />
            <Route path="/evaluation/runs/:runId" element={<RunDetailPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </ErrorBoundary>
      </main>
    </div>
  );
}
