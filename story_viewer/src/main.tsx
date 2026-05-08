import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { StoryListPage } from "./pages/StoryListPage";
import { PipelineViewPage } from "./pages/PipelineViewPage";
import { TemplateEditorPage } from "./pages/TemplateEditorPage";
import { PromptInspectorPage } from "./pages/PromptInspectorPage";
import { ProjectListPage } from "./pages/ProjectListPage";
import { ProjectPage } from "./pages/ProjectPage";
import { CharacterEditorPage } from "./pages/CharacterEditorPage";
import { Navigate } from "react-router-dom";
import "./main.css";

function App() {
  return (
    <BrowserRouter>
      <nav className="topnav">
        <span className="logo">valmiki</span>
        <NavLink to="/" end>Worlds</NavLink>
        <NavLink to="/stories">Stories</NavLink>
        <NavLink to="/inspector">Inspector</NavLink>
        <NavLink to="/templates">Templates</NavLink>
        <NavLink to="/pipeline">Pipeline</NavLink>
      </nav>
      <main className="main-content">
        <Routes>
          <Route path="/" element={<ProjectListPage />} />
          <Route path="/stories" element={<StoryListPage />} />
          <Route path="/pipeline" element={<PipelineViewPage />} />
          <Route path="/pipeline/:runId" element={<PipelineViewPage />} />
          <Route path="/templates" element={<TemplateEditorPage />} />
          <Route path="/templates/:path" element={<TemplateEditorPage />} />
          <Route path="/inspector" element={<PromptInspectorPage />} />
          <Route path="/inspector/:runId" element={<PromptInspectorPage />} />
          <Route path="/inspector/:runId/:stage" element={<PromptInspectorPage />} />
          <Route path="/characters" element={<ProjectListPage />} />
          <Route path="/w/:projectId" element={<ProjectPage />} />
          <Route path="/w/:projectId/t/:templateId" element={<Navigate to=".." replace />} />
          <Route path="/w/:projectId/t/:templateId/c/:characterId" element={<CharacterEditorPage />} />
          {/* legacy deep links */}
          <Route path="/characters/:projectId" element={<ProjectPage />} />
          <Route path="/characters/:projectId/t/:templateId" element={<Navigate to=".." replace />} />
          <Route path="/characters/:projectId/t/:templateId/c/:characterId" element={<CharacterEditorPage />} />
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
