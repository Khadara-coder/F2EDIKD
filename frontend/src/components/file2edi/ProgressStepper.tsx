import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface Step {
  id: string;
  label: string;
  status: "completed" | "current" | "pending";
}

interface ProgressStepperProps {
  steps: Step[];
  orientation?: "horizontal" | "vertical";
  className?: string;
}

export function ProgressStepper({
  steps,
  orientation = "vertical",
  className,
}: ProgressStepperProps) {
  if (orientation === "horizontal") {
    return (
      <div className={cn("flex items-center gap-2", className)}>
        {steps.map((step, i) => (
          <div key={step.id} className="flex items-center gap-2">
            <StepCircle step={step} />
            <span
              className={cn(
                "text-xs whitespace-nowrap",
                step.status === "current" && "font-semibold text-primary",
                step.status === "completed" && "text-emerald-600",
                step.status === "pending" && "text-muted-foreground",
              )}
            >
              {step.label}
            </span>
            {i < steps.length - 1 && (
              <div className="mx-1 h-px w-6 bg-border" />
            )}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={cn("space-y-0", className)}>
      {steps.map((step, i) => (
        <div key={step.id} className="flex gap-3">
          <div className="flex flex-col items-center">
            <StepCircle step={step} />
            {i < steps.length - 1 && (
              <div
                className={cn(
                  "w-0.5 flex-1 min-h-[20px]",
                  step.status === "completed" ? "bg-emerald-500" : "bg-border",
                )}
              />
            )}
          </div>
          <div className="pb-4 pt-0.5">
            <p
              className={cn(
                "text-sm",
                step.status === "current" && "font-semibold text-primary",
                step.status === "completed" && "text-foreground",
                step.status === "pending" && "text-muted-foreground",
              )}
            >
              {step.label}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function StepCircle({ step }: { step: Step }) {
  if (step.status === "completed") {
    return (
      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-500 text-white">
        <Check className="h-4 w-4" />
      </div>
    );
  }
  if (step.status === "current") {
    return (
      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs font-bold text-white">
        {step.id}
      </div>
    );
  }
  return (
    <div className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-border bg-white text-xs text-muted-foreground" />
  );
}
