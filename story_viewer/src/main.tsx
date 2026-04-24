import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { StoryListPage } from "./pages/StoryListPage";
import { PipelineViewPage } from "./pages/PipelineViewPage";
import { TemplateEditorPage } from "./pages/TemplateEditorPage";
import { PromptInspectorPage } from "./pages/PromptInspectorPage";
import "./main.css";

function App() {
  return (
    <BrowserRouter>
      <nav className="topnav">
        <span className="logo">valmiki</span>
        <NavLink to="/">Stories</NavLink>
        <NavLink to="/pipeline">Pipeline</NavLink>
        <NavLink to="/templates">Templates</NavLink>
        <NavLink to="/inspector">Inspector</NavLink>
      </nav>
      <main className="main-content">
        <Routes>
          <Route path="/" element={<StoryListPage />} />
          <Route path="/pipeline" element={<PipelineViewPage />} />
          <Route path="/pipeline/:runId" element={<PipelineViewPage />} />
          <Route path="/templates" element={<TemplateEditorPage />} />
          <Route path="/templates/:path" element={<TemplateEditorPage />} />
          <Route path="/inspector" element={<PromptInspectorPage />} />
          <Route path="/inspector/:runId" element={<PromptInspectorPage />} />
          <Route path="/inspector/:runId/:stage" element={<PromptInspectorPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
