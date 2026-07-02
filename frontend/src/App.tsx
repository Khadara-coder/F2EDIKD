import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PageContainer } from "@/components/layout/PageContainer";
import { useCurrentUser, hasAtLeastRole } from "@/hooks/useCurrentUser";
import { ApiError } from "@/lib/api";
import { CockpitPage } from "@/pages/CockpitPage";
import { ConvertirPage } from "@/pages/ConvertirPage";
import { RevueListPage } from "@/pages/RevueListPage";
import { RevuePage } from "@/pages/RevuePage";
import { HistoriquePage } from "@/pages/HistoriquePage";
import { DonneesMaitresPage } from "@/pages/DonneesMaitresPage";
import { ParametresPage } from "@/pages/ParametresPage";
import { LoginPage } from "@/pages/LoginPage";
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

function isUnauthorized(error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.status === 401;
  }
  if (error instanceof Error) {
    return /401|unauthorized|authentification requise/i.test(error.message);
  }
  return false;
}

function AppContent() {
  const meQuery = useCurrentUser();

  if (meQuery.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="text-sm text-muted-foreground">Chargement de la session utilisateur...</div>
      </div>
    );
  }

  if (isUnauthorized(meQuery.error) || meQuery.data?.authenticated === false) {
    return (
      <BrowserRouter>
        <Routes>
          <Route path="*" element={<LoginPage />} />
        </Routes>
      </BrowserRouter>
    );
  }

  if (meQuery.error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <div className="max-w-lg text-center">
          <h1 className="text-xl font-semibold">Impossible de charger la session</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Vérifie la connectivité Databricks puis recharge la page.
          </p>
        </div>
      </div>
    );
  }

  return (
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
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
    </QueryClientProvider>
  );
}
