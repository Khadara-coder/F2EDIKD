import { LoaderCircle } from "lucide-react";

import { cn } from "@/lib/utils";

type LoadingStateProps = {
  label?: string;
  className?: string;
  fullScreen?: boolean;
};

export function LoadingState({
  label = "Chargement…",
  className,
  fullScreen = false,
}: LoadingStateProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex items-center justify-center gap-2 text-sm text-muted-foreground",
        fullScreen ? "min-h-screen bg-background" : "py-6",
        className,
      )}
    >
      <LoaderCircle className="size-4 animate-spin text-primary" aria-hidden="true" />
      <span>{label}</span>
      <span className="sr-only">En cours</span>
    </div>
  );
}

export function LoadingBar({ className }: { className?: string }) {
  return (
    <div
      role="progressbar"
      aria-label="Chargement en cours"
      className={cn("h-0.5 w-full overflow-hidden bg-muted", className)}
    >
      <div className="h-full w-1/3 animate-[loading-bar_1.2s_ease-in-out_infinite] bg-primary" />
    </div>
  );
}
