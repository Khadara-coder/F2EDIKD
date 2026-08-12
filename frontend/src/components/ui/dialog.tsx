import * as React from "react";
import { cn } from "@/lib/utils";

interface DialogProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  children?: React.ReactNode;
}

export function Dialog({ open, onOpenChange, children }: DialogProps) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4">
      <div
        className="fixed inset-0 bg-black/40"
        onClick={() => onOpenChange?.(false)}
      />
      <div className="relative z-50 flex max-h-[92vh] w-full justify-center overflow-y-auto sm:max-h-[90vh]">
        {children}
      </div>
    </div>
  );
}

export function DialogContent({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "mx-0 w-full max-w-md rounded-t-lg border bg-background p-4 shadow-xl sm:mx-4 sm:rounded-lg sm:p-6",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function DialogHeader({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mb-4", className)} {...props}>{children}</div>;
}

export function DialogTitle({ className, children, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn("text-lg font-semibold", className)} {...props}>{children}</h2>;
}

export function DialogFooter({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex justify-end gap-2 mt-4", className)} {...props}>{children}</div>;
}
