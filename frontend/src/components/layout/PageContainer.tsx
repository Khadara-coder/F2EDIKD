import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { SidebarProvider } from "./SidebarContext";

interface PageContainerProps {
  children: ReactNode;
}

export function PageContainer({ children }: PageContainerProps) {
  return (
    <SidebarProvider>
      <div className="min-h-screen overflow-x-hidden bg-background">
        <Sidebar />
        <main className="min-h-screen px-4 pb-8 pt-4 sm:px-6 sm:pt-6 lg:ml-[260px] lg:px-8 lg:pb-8 lg:pt-10">
          {children}
        </main>
      </div>
    </SidebarProvider>
  );
}
