import { useEffect, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { UploadQueueProvider } from "@/hooks/useUploadQueue";
import { Sidebar } from "./Sidebar";
import { SidebarProvider } from "./SidebarContext";

interface PageContainerProps {
  children: ReactNode;
}

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

export function PageContainer({ children }: PageContainerProps) {
  return (
    <SidebarProvider>
      <UploadQueueProvider>
        <ScrollToTop />
        <div className="min-h-dvh bg-background">
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[60] focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:shadow"
          >
            Aller au contenu
          </a>
          <Sidebar />
          <main
            id="main-content"
            tabIndex={-1}
            className="min-h-dvh px-3 pb-24 pt-3 sm:px-5 sm:pb-10 sm:pt-5 lg:ml-[260px] lg:px-8 lg:pb-8 lg:pt-8"
          >
            {children}
          </main>
        </div>
      </UploadQueueProvider>
    </SidebarProvider>
  );
}
