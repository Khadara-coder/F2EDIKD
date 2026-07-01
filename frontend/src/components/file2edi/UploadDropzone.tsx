import { useCallback, useState } from "react";
import { FileText, Upload } from "lucide-react";
import { cn } from "@/lib/utils";

interface UploadDropzoneProps {
  onFileSelect: (file: File) => void;
  disabled?: boolean;
  className?: string;
}

export function UploadDropzone({ onFileSelect, disabled, className }: UploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);

  const handleFile = useCallback(
    (file: File) => {
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        alert("Seuls les fichiers PDF sont acceptés.");
        return;
      }
      if (file.size > 20 * 1024 * 1024) {
        alert("Le fichier dépasse la limite de 20 Mo.");
        return;
      }
      onFileSelect(file);
    },
    [onFileSelect],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      if (disabled) return;
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [disabled, handleFile],
  );

  return (
    <div
      className={cn(
        "relative flex min-h-[220px] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed transition-colors",
        isDragging
          ? "border-primary bg-primary/5"
          : "border-slate-300 bg-white hover:border-primary/50 hover:bg-slate-50",
        disabled && "pointer-events-none opacity-50",
        className,
      )}
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={onDrop}
      onClick={() => {
        if (disabled) return;
        const input = document.createElement("input");
        input.type = "file";
        input.accept = ".pdf";
        input.onchange = () => {
          const file = input.files?.[0];
          if (file) handleFile(file);
        };
        input.click();
      }}
    >
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
        <FileText className="h-8 w-8 text-primary" />
      </div>
      <p className="mt-4 text-base font-semibold text-foreground">Glisser un PDF ici</p>
      <p className="mt-1 text-sm text-muted-foreground">
        ou cliquez pour sélectionner un fichier
      </p>
      <p className="mt-2 text-xs text-muted-foreground">Fichier PDF uniquement, max 20 Mo</p>
      <Upload className="absolute right-4 top-4 h-5 w-5 text-muted-foreground/40" />
    </div>
  );
}
