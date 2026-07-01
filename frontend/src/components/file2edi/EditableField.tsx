import { useState } from "react";
import { Check, Pencil, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface EditableFieldProps {
  label: string;
  value: string;
  onSave: (value: string) => Promise<void> | void;
  type?: "text" | "date" | "number";
  manuallyEdited?: boolean;
  className?: string;
  invalid?: boolean;
}

export function EditableField({
  label,
  value,
  onSave,
  type = "text",
  manuallyEdited,
  className,
  invalid,
}: EditableFieldProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
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

  return (
    <div className={cn("group space-y-1", className)}>
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        {manuallyEdited && (
          <Badge variant="info" className="text-[10px] px-1.5 py-0">
            Modifié manuellement
          </Badge>
        )}
      </div>
      {editing ? (
        <div className="flex items-center gap-2">
          <Input
            type={type}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="h-8 text-sm"
            autoFocus
          />
          <Button size="icon" variant="ghost" className="h-8 w-8" onClick={handleSave} disabled={saving}>
            <Check className="h-4 w-4 text-emerald-600" />
          </Button>
          <Button size="icon" variant="ghost" className="h-8 w-8" onClick={handleCancel}>
            <X className="h-4 w-4 text-red-600" />
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "text-sm font-medium",
              invalid && "text-red-600",
            )}
          >
            {value || "—"}
          </span>
          <button
            type="button"
            onClick={() => {
              setDraft(value);
              setEditing(true);
            }}
            className="opacity-0 group-hover:opacity-100 transition-opacity rounded p-1 hover:bg-muted"
          >
            <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
        </div>
      )}
    </div>
  );
}
