import { Navigate, Route, Routes } from 'react-router-dom'
import { Shell } from './shell/Shell'
import { ProjectListPage } from './routes/ProjectListPage'
import { EditRoute, EditWorkspaceRoute } from './routes/EditRoute'
import { PlaceholderPage } from './routes/PlaceholderPage'
import { IngestPage } from './ingest/IngestPage'
import { NewProjectPage } from './ingest/NewProjectPage'

export function App() {
  return (
    <Routes>
      <Route path="/" element={<ProjectListPage />} />
      <Route path="/new" element={<NewProjectPage />} />
      <Route path="/p/:pid" element={<Shell />}>
        <Route index element={<Navigate to="edit" replace />} />
        <Route path="ingest" element={<IngestPage />} />
        <Route path="edit" element={<EditRoute />} />
        <Route path="edit/:cutId" element={<EditWorkspaceRoute />} />
        <Route path="deliver" element={<PlaceholderPage label="Deliver" />} />
      </Route>
    </Routes>
  )
}
