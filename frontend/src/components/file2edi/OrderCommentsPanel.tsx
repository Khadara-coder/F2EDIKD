import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTime } from "@/lib/utils";
import type { OrderAnomaly, OrderComment } from "@/types";

interface OrderCommentsPanelProps {
  comments: OrderComment[];
  anomalies: OrderAnomaly[];
  selectedAnomalyId: string | null;
  onClearSelection: () => void;
  onSubmit: (body: string, anomalyId: string | null) => Promise<void>;
  disabled?: boolean;
}

export function OrderCommentsPanel({
  comments,
  anomalies,
  selectedAnomalyId,
  onClearSelection,
  onSubmit,
  disabled,
}: OrderCommentsPanelProps) {
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const selected = anomalies.find((a) => a.anomalyId === selectedAnomalyId);
  const linkedLabel = selected
    ? (selected.message.length > 80 ? `${selected.message.slice(0, 80)}…` : selected.message)
    : null;

  const handleSubmit = async () => {
    const body = draft.trim();
    if (!body || pending || disabled) return;
    setPending(true);
    try {
      await onSubmit(body, selectedAnomalyId);
      setDraft("");
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="space-y-3 border-t pt-4">
      <p className="text-sm font-medium text-foreground">Notes de revue</p>
      {comments.length === 0 ? (
        <p className="text-sm text-muted-foreground">Aucun commentaire pour l&apos;instant.</p>
      ) : (
        <ul className="max-h-56 space-y-2 overflow-y-auto">
          {[...comments].reverse().map((c) => {
            const linked = anomalies.find((a) => a.anomalyId === c.anomalyId);
            return (
              <li key={c.commentId} className="rounded-lg border bg-muted/20 px-3 py-2">
                <p className="text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">{c.actor}</span>
                  {" · "}
                  {c.createdAt ? formatDateTime(c.createdAt) : ""}
                  {linked ? " · lié à une anomalie" : ""}
                </p>
                {linked && (
                  <p className="mt-0.5 truncate text-xs text-amber-800" title={linked.message}>
                    {linked.message}
                  </p>
                )}
                <p className="mt-1 whitespace-pre-wrap text-sm">{c.body}</p>
              </li>
            );
          })}
        </ul>
      )}

      <div className="space-y-2">
        {linkedLabel && (
          <p className="text-xs text-amber-800">
            Le commentaire sera rattaché à : {linkedLabel}
            {" — "}
            <button type="button" className="underline" onClick={onClearSelection}>
              dossier entier
            </button>
          </p>
        )}
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={
            selected
              ? "Commentaire sur l'anomalie sélectionnée…"
              : "Ajouter un commentaire sur le dossier…"
          }
          disabled={disabled || pending}
          rows={3}
        />
        <div className="flex justify-end">
          <Button
            size="sm"
            onClick={() => void handleSubmit()}
            disabled={disabled || pending || !draft.trim()}
          >
            {pending ? "Ajout…" : "Ajouter"}
          </Button>
        </div>
      </div>
    </div>
  );
}
