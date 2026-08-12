import { CheckCircle2, Clock, Loader2, XCircle } from "lucide-react";
import type { UploadJob } from "@/hooks/useUploadQueue";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface UploadQueuePanelProps {
  jobs: UploadJob[];
  selectedJobId: string | null;
  onSelectJob: (jobId: string) => void;
  onNavigateToReview: (orderId: string) => void;
}

const statusMeta = {
  queued: { label: "En attente", icon: Clock, className: "text-muted-foreground" },
  uploading: { label: "Envoi…", icon: Loader2, className: "text-primary" },
  extracting: { label: "Extraction…", icon: Loader2, className: "text-primary" },
  done: { label: "Terminé", icon: CheckCircle2, className: "text-emerald-600" },
  error: { label: "Erreur", icon: XCircle, className: "text-red-600" },
} as const;

export function UploadQueuePanel({
  jobs,
  selectedJobId,
  onSelectJob,
  onNavigateToReview,
}: UploadQueuePanelProps) {
  if (!jobs.length) return null;

  return (
    <div className="overflow-hidden rounded-xl border bg-white">
      <div className="border-b bg-muted/20 px-4 py-3">
        <p className="text-sm font-semibold text-foreground">File d&apos;attente</p>
        <p className="text-xs text-muted-foreground">
          {jobs.length} document{jobs.length > 1 ? "s" : ""} — vous pouvez en déposer d&apos;autres
          pendant le traitement.
        </p>
      </div>
      <ul className="divide-y">
        {jobs.map((job) => {
          const meta = statusMeta[job.status];
          const Icon = meta.icon;
          const isActive = job.status === "uploading" || job.status === "extracting";
          const isSelectable = job.status === "done" && job.preview;

          return (
            <li
              key={job.id}
              className={cn(
                "flex flex-wrap items-center justify-between gap-3 px-4 py-3",
                selectedJobId === job.id && "bg-primary/5",
              )}
            >
              <button
                type="button"
                className={cn(
                  "flex min-w-0 flex-1 items-center gap-3 text-left",
                  isSelectable ? "cursor-pointer" : "cursor-default",
                )}
                onClick={() => {
                  if (isSelectable) onSelectJob(job.id);
                }}
                disabled={!isSelectable}
              >
                <Icon
                  className={cn(
                    "h-4 w-4 shrink-0",
                    meta.className,
                    isActive && "animate-spin",
                  )}
                />
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-foreground">{job.fileName}</p>
                  {job.error ? (
                    <p className="truncate text-xs text-red-600">{job.error}</p>
                  ) : job.preview ? (
                    <p className="truncate text-xs text-muted-foreground">
                      {job.preview.clientName || "Client non identifié"} — {job.preview.lineCount}{" "}
                      ligne{job.preview.lineCount > 1 ? "s" : ""}
                    </p>
                  ) : (
                    <p className="text-xs text-muted-foreground">{meta.label}</p>
                  )}
                </div>
              </button>

              <div className="flex items-center gap-2">
                <Badge variant={job.status === "error" ? "destructive" : "secondary"}>
                  {meta.label}
                </Badge>
                {job.orderId && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onNavigateToReview(job.orderId!)}
                  >
                    Revue
                  </Button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
