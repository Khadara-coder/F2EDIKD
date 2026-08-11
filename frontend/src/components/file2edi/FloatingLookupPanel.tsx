import { createPortal } from "react-dom";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { cn } from "@/lib/utils";

interface FloatingLookupPanelProps {
  anchorRef: RefObject<HTMLElement | null>;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  className?: string;
  minWidth?: number;
}

export function FloatingLookupPanel({
  anchorRef,
  open,
  onClose,
  children,
  className,
  minWidth = 300,
}: FloatingLookupPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [style, setStyle] = useState<React.CSSProperties>({});

  useLayoutEffect(() => {
    if (!open || !anchorRef.current) return;

    const updatePosition = () => {
      const anchor = anchorRef.current;
      if (!anchor) return;

      const rect = anchor.getBoundingClientRect();
      const panelHeight = panelRef.current?.offsetHeight ?? 280;
      const gap = 6;
      const spaceBelow = window.innerHeight - rect.bottom - gap;
      const spaceAbove = rect.top - gap;
      const openAbove = spaceBelow < panelHeight && spaceAbove > spaceBelow;
      const width = Math.max(rect.width, minWidth);
      const left = Math.min(rect.left, window.innerWidth - width - 8);

      setStyle({
        position: "fixed",
        left: Math.max(8, left),
        top: openAbove ? rect.top - gap : rect.bottom + gap,
        transform: openAbove ? "translateY(-100%)" : undefined,
        width,
        zIndex: 100,
      });
    };

    updatePosition();
    const raf = requestAnimationFrame(updatePosition);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open, anchorRef, minWidth, children]);

  useEffect(() => {
    if (!open) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (anchorRef.current?.contains(target)) return;
      if (panelRef.current?.contains(target)) return;
      onClose();
    };

    window.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [open, onClose, anchorRef]);

  if (!open) return null;

  return createPortal(
    <div
      ref={panelRef}
      style={style}
      className={cn(
        "rounded-md border bg-popover p-2 shadow-lg",
        className,
      )}
      role="dialog"
      aria-modal="true"
    >
      {children}
    </div>,
    document.body,
  );
}
