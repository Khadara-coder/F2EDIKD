import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface MotifTemplateFieldProps {
  id?: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  templates: readonly string[];
  placeholder?: string;
  rows?: number;
  required?: boolean;
}

export function MotifTemplateField({
  id,
  label,
  value,
  onChange,
  templates,
  placeholder = "Saisir un motif personnalisé…",
  rows = 3,
  required = true,
}: MotifTemplateFieldProps) {
  const trimmed = value.trim();

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        <Label htmlFor={id}>{label}{required ? " *" : ""}</Label>
        <p className="text-xs text-muted-foreground">
          Choisissez un motif prédéfini ou rédigez le vôtre ci-dessous.
        </p>
        <div className="flex flex-wrap gap-1.5">
          {templates.map((template) => {
            const selected = trimmed === template;
            return (
              <Button
                key={template}
                type="button"
                variant={selected ? "default" : "outline"}
                size="sm"
                className={cn(
                  "h-auto whitespace-normal px-2.5 py-1.5 text-left text-xs font-normal leading-snug",
                  !selected && "text-foreground",
                )}
                onClick={() => onChange(selected ? "" : template)}
              >
                {template}
              </Button>
            );
          })}
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={id} className="text-xs text-muted-foreground">
          {required ? "Motif personnalisé" : "Note personnalisée"}
        </Label>
        <Textarea
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          rows={rows}
        />
      </div>
    </div>
  );
}
