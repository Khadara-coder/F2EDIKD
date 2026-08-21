import { useEffect, useState } from "react";
import { Check, Pencil, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn, formatDate } from "@/lib/utils";
import { useFocusWithoutScroll } from "@/hooks/useFocusWithoutScroll";

import type { PartnerEditSource } from "@/types";

interface EditableFieldProps {
  label: string;
  value: string;
  onSave?: (value: string) => Promise<void> | void;
  type?: "text" | "date" | "number";
  manuallyEdited?: boolean;
  editFlag?: PartnerEditSource;
  className?: string;
  invalid?: boolean;
  errorMessage?: string;
  fieldId?: string;
  readOnly?: boolean;
}

export function EditableField({
  label,
  value,
  onSave,
  type = "text",
  manuallyEdited,
  editFlag,
  className,
  invalid,
  errorMessage,
  fieldId,
  readOnly = false,
}: EditableFieldProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const inputRef = useFocusWithoutScroll<HTMLInputElement>(editing && !readOnly);
  const errorId = fieldId ? `${fieldId}-error` : undefined;

  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  const handleSave = async () => {
    if (!onSave) return;
    setSaving(true);
    try {
      await onSave(draft);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setDraft(value);
    setEditing(false);
  };

  const flag = editFlag ?? (manuallyEdited ? "manual" : undefined);
  const displayValue = type === "date" ? formatDate(value) : (value || "-");

  return (
    <div
      className={cn("group space-y-1", className)}
      id={fieldId}
      tabIndex={fieldId ? -1 : undefined}
    >
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground" id={fieldId ? `${fieldId}-label` : undefined}>
          {label}
        </span>
        {flag === "manual" && (
          <Badge variant="info" className="text-[10px] px-1.5 py-0">
            Modifié manuellement
          </Badge>
        )}
        {flag === "auto" && (
          <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
            Modifié automatiquement
          </Badge>
        )}
      </div>
      {editing && !readOnly ? (
        <div className="flex items-center gap-2">
          <Input
            ref={inputRef}
            type={type}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="h-8 text-sm"
            aria-invalid={invalid || undefined}
            aria-describedby={invalid && errorId ? errorId : undefined}
            aria-labelledby={fieldId ? `${fieldId}-label` : undefined}
          />
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            onClick={handleSave}
            disabled={saving}
            aria-label={`Enregistrer ${label}`}
          >
            <Check className="h-4 w-4 text-emerald-600" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            onClick={handleCancel}
            aria-label={`Annuler la modification de ${label}`}
          >
            <X className="h-4 w-4 text-red-600" />
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "text-sm font-medium",
              invalid && "text-red-600",
              readOnly && "text-muted-foreground",
            )}
            aria-invalid={invalid || undefined}
          >
            {displayValue}
          </span>
          {!readOnly && onSave && (
            <button
              type="button"
              id={fieldId ? `${fieldId}-edit` : undefined}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setDraft(value);
                setEditing(true);
              }}
              className="rounded p-1 opacity-0 transition-opacity hover:bg-muted focus:opacity-100 group-hover:opacity-100"
              aria-label={`Modifier ${label}`}
            >
              <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
            </button>
          )}
        </div>
      )}
      {invalid && errorMessage && (
        <p id={errorId} className="text-xs text-destructive" role="alert">
          {errorMessage}
        </p>
      )}
    </div>
  );
}
