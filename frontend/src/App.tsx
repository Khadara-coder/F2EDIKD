import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PageContainer } from "@/components/layout/PageContainer";
import { CockpitPage } from "@/pages/CockpitPage";
import { ConvertirPage } from "@/pages/ConvertirPage";
import { RevueListPage } from "@/pages/RevueListPage";
import { RevuePage } from "@/pages/RevuePage";
import { HistoriquePage } from "@/pages/HistoriquePage";
import { DonneesMaitresPage } from "@/pages/DonneesMaitresPage";
import { ParametresPage } from "@/pages/ParametresPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <PageContainer>
          <Routes>
            <Route path="/" element={<CockpitPage />} />
            <Route path="/convertir" element={<ConvertirPage />} />
            <Route path="/revue" element={<RevueListPage />} />
            <Route path="/revue/:orderId" element={<RevuePage />} />
            <Route path="/historique" element={<HistoriquePage />} />
            <Route path="/donnees-maitres" element={<DonneesMaitresPage />} />
            <Route path="/parametres" element={<ParametresPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </PageContainer>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
