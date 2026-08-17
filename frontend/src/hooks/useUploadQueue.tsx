import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ExtractionPreview } from "@/types";

export type UploadJobStatus = "queued" | "uploading" | "extracting" | "done" | "error";

export interface UploadJob {
  id: string;
  file: File;
  fileName: string;
  status: UploadJobStatus;
  uploadId?: string;
  orderId?: string;
  preview?: ExtractionPreview;
  error?: string;
}

interface UploadQueueContextValue {
  jobs: UploadJob[];
  activeCount: number;
  enqueueFiles: (files: File[]) => void;
  selectedJob: UploadJob | null;
  selectedJobId: string | null;
  setSelectedJobId: (id: string) => void;
}

const UploadQueueContext = createContext<UploadQueueContextValue | null>(null);

export function UploadQueueProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const jobsRef = useRef<UploadJob[]>([]);
  const workerRunning = useRef(false);

  const syncJobs = useCallback((updater: (prev: UploadJob[]) => UploadJob[]) => {
    setJobs((prev) => {
      const next = updater(prev);
      jobsRef.current = next;
      return next;
    });
  }, []);

  const updateJob = useCallback(
    (id: string, patch: Partial<UploadJob>) => {
      syncJobs((prev) => prev.map((job) => (job.id === id ? { ...job, ...patch } : job)));
    },
    [syncJobs],
  );

  const onJobComplete = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["orders"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  }, [queryClient]);

  const runWorker = useCallback(async () => {
    if (workerRunning.current) return;
    workerRunning.current = true;

    try {
      while (true) {
        const next = jobsRef.current.find((job) => job.status === "queued");
        if (!next) break;

        updateJob(next.id, { status: "uploading" });
        try {
          const { uploadId } = await api.uploadPdf(next.file);
          updateJob(next.id, { status: "extracting", uploadId });
          const preview = await api.launchExtractionJob(uploadId);
          updateJob(next.id, {
            status: "done",
            preview,
            orderId: preview.orderId,
          });
          setSelectedJobId(next.id);
          onJobComplete();
        } catch (err) {
          updateJob(next.id, {
            status: "error",
            error: err instanceof Error ? err.message : "Échec de l'extraction",
          });
        }
      }
    } finally {
      workerRunning.current = false;
      if (jobsRef.current.some((job) => job.status === "queued")) {
        void runWorker();
      }
    }
  }, [onJobComplete, updateJob]);

  const enqueueFiles = useCallback(
    (files: File[]) => {
      if (!files.length) return;

      const newJobs: UploadJob[] = files.map((file) => ({
        id: crypto.randomUUID(),
        file,
        fileName: file.name,
        status: "queued",
      }));

      syncJobs((prev) => [...prev, ...newJobs]);
      void runWorker();
    },
    [runWorker, syncJobs],
  );

  const selectedJob =
    jobs.find((job) => job.id === selectedJobId && job.preview) ??
    [...jobs].reverse().find((job) => job.preview) ??
    null;

  const activeCount = jobs.filter((job) =>
    ["queued", "uploading", "extracting"].includes(job.status),
  ).length;

  const value = useMemo<UploadQueueContextValue>(
    () => ({
      jobs,
      activeCount,
      enqueueFiles,
      selectedJob,
      selectedJobId: selectedJob?.id ?? selectedJobId,
      setSelectedJobId,
    }),
    [activeCount, enqueueFiles, jobs, selectedJob, selectedJobId],
  );

  return <UploadQueueContext.Provider value={value}>{children}</UploadQueueContext.Provider>;
}

export function useUploadQueue() {
  const ctx = useContext(UploadQueueContext);
  if (!ctx) {
    throw new Error("useUploadQueue must be used within UploadQueueProvider");
  }
  return ctx;
}
