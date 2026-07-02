import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";

interface PageContainerProps {
  children: ReactNode;
}

export function PageContainer({ children }: PageContainerProps) {
  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <main className="ml-[260px] min-h-screen px-8 pb-8 pt-10">{children}</main>
    </div>
  );
}
