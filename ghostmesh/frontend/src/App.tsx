import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from './layout';
import { OverviewPage } from './pages/OverviewPage';
import { SearchPage } from './pages/SearchPage';
import { ReconPage } from './pages/ReconPage';
import { BrowserPage } from './pages/BrowserPage';
import { TechSniperPage } from './pages/TechSniperPage';
import { ArchivePage } from './pages/ArchivePage';
import { MetadataPage } from './pages/MetadataPage';
import { EntitiesPage } from './pages/EntitiesPage';
import { PeopleFinderPage } from './pages/PeopleFinderPage';
import { ImageSearchPage } from './pages/ImageSearchPage';
import { ExtractPage } from './pages/ExtractPage';
import { GraphPage } from './pages/GraphPage';
import { FrameworkPage } from './pages/FrameworkPage';
import { ReportsPage } from './pages/ReportsPage';
import { SettingsPage } from './pages/SettingsPage';
import { HubPage } from './pages/HubPage';

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

// Listens for navigate IPC events from the Electron main process menu items.
// No-op in browser mode (window.jarvisOS is undefined).
function ElectronNavigationBridge() {
  const navigate = useNavigate();

  useEffect(() => {
    const api = (window as unknown as { jarvisOS?: { onNavigate?: (cb: (route: string) => void) => () => void } }).jarvisOS;
    if (!api?.onNavigate) return;
    const unsub = api.onNavigate((route) => navigate(route));
    return unsub;
  }, [navigate]);

  return null;
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <ElectronNavigationBridge />
        <Layout>
          <Routes>
            <Route path="/modules" element={<HubPage />} />
            <Route path="/" element={<OverviewPage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/recon" element={<ReconPage />} />
            <Route path="/recon/browser" element={<BrowserPage />} />
            <Route path="/recon/tech" element={<TechSniperPage />} />
            <Route path="/recon/archive" element={<ArchivePage />} />
            <Route path="/recon/metadata" element={<MetadataPage />} />
            <Route path="/entities" element={<EntitiesPage />} />
            <Route path="/entities/people" element={<PeopleFinderPage />} />
            <Route path="/entities/images" element={<ImageSearchPage />} />
            <Route path="/entities/extract" element={<ExtractPage />} />
            <Route path="/entities/graph" element={<GraphPage />} />
            <Route path="/framework" element={<FrameworkPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
