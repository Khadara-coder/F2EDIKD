import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PageContainer } from "@/components/layout/PageContainer";
import { useCurrentUser, hasAtLeastRole } from "@/hooks/useCurrentUser";
import { CockpitPage } from "@/pages/CockpitPage";
import { ConvertirPage } from "@/pages/ConvertirPage";
import { RevueListPage } from "@/pages/RevueListPage";
import { RevuePage } from "@/pages/RevuePage";
import { HistoriquePage } from "@/pages/HistoriquePage";
import { DonneesMaitresPage } from "@/pages/DonneesMaitresPage";
import { ParametresPage } from "@/pages/ParametresPage";
import type { AppRole } from "@/types";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

function GuardedRoute({ minRole, children }: { minRole: AppRole; children: JSX.Element }) {
  const { data: me, isLoading } = useCurrentUser();

  if (isLoading) {
    return <div className="p-6 text-sm text-muted-foreground">Chargement du profil utilisateur...</div>;
  }

  if (!hasAtLeastRole(me?.role, minRole)) {
    return <Navigate to="/" replace />;
  }

  return children;
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <PageContainer>
          <Routes>
            <Route path="/" element={<CockpitPage />} />
            <Route
              path="/convertir"
              element={
                <GuardedRoute minRole="operator">
                  <ConvertirPage />
                </GuardedRoute>
              }
            />
            <Route
              path="/revue"
              element={
                <GuardedRoute minRole="reviewer">
                  <Outlet />
                </GuardedRoute>
              }
            >
              <Route index element={<RevueListPage />} />
              <Route path=":orderId" element={<RevuePage />} />
            </Route>
            <Route path="/historique" element={<HistoriquePage />} />
            <Route
              path="/donnees-maitres"
              element={
                <GuardedRoute minRole="reviewer">
                  <DonneesMaitresPage />
                </GuardedRoute>
              }
            />
            <Route
              path="/parametres"
              element={
                <GuardedRoute minRole="admin">
                  <ParametresPage />
                </GuardedRoute>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </PageContainer>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
