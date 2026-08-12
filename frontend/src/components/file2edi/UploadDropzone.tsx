import { useCallback, useState } from "react";
import { FileText, Upload } from "lucide-react";
import { cn } from "@/lib/utils";

const MAX_FILE_SIZE = 20 * 1024 * 1024;
const MAX_FILES_PER_DROP = 20;

interface UploadDropzoneProps {
  onFilesSelect: (files: File[]) => void;
  disabled?: boolean;
  className?: string;
}

function validatePdfFiles(files: FileList | File[]): File[] {
  const valid: File[] = [];
  const errors: string[] = [];

  for (const file of Array.from(files)) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      errors.push(`${file.name} : seuls les PDF sont acceptés.`);
      continue;
    }
    if (file.size > MAX_FILE_SIZE) {
      errors.push(`${file.name} : dépasse la limite de 20 Mo.`);
      continue;
    }
    valid.push(file);
  }

  if (errors.length) {
    alert(errors.join("\n"));
  }

  if (valid.length > MAX_FILES_PER_DROP) {
    alert(`Maximum ${MAX_FILES_PER_DROP} fichiers PDF par dépôt.`);
    return valid.slice(0, MAX_FILES_PER_DROP);
  }

  return valid;
}

export function UploadDropzone({ onFilesSelect, disabled, className }: UploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);

  const handleFiles = useCallback(
    (incoming: FileList | File[]) => {
      const files = validatePdfFiles(incoming);
      if (files.length) onFilesSelect(files);
    },
    [onFilesSelect],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      if (disabled) return;
      if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
    },
    [disabled, handleFiles],
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
        input.multiple = true;
        input.onchange = () => {
          if (input.files?.length) handleFiles(input.files);
        };
        input.click();
      }}
    >
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
        <FileText className="h-8 w-8 text-primary" />
      </div>
      <p className="mt-4 text-base font-semibold text-foreground">Glisser des PDF ici</p>
      <p className="mt-1 text-sm text-muted-foreground">
        ou cliquez pour sélectionner un ou plusieurs fichiers
      </p>
      <p className="mt-2 text-xs text-muted-foreground">
        PDF uniquement, max 20 Mo par fichier, {MAX_FILES_PER_DROP} fichiers max par dépôt
      </p>
      <Upload className="absolute right-4 top-4 h-5 w-5 text-muted-foreground/40" />
    </div>
  );
}
