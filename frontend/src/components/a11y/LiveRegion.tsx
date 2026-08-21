import { useCallback, useEffect, useRef, useState } from "react";

interface LiveRegionProps {
  message: string;
  politeness?: "polite" | "assertive";
}

/** Screen-reader announcements; visually hidden. */
export function LiveRegion({ message, politeness = "polite" }: LiveRegionProps) {
  return (
    <div
      role="status"
      aria-live={politeness}
      aria-atomic="true"
      className="sr-only"
    >
      {message}
    </div>
  );
}

/** Hook to announce short status messages to assistive tech. */
export function useLiveAnnounce() {
  const [message, setMessage] = useState("");
  const clearTimer = useRef<number | null>(null);

  const announce = useCallback((text: string) => {
    const next = (text || "").trim();
    if (!next) return;
    if (clearTimer.current) {
      window.clearTimeout(clearTimer.current);
    }
    // Retrigger announcement when the same text is repeated.
    setMessage("");
    window.requestAnimationFrame(() => {
      setMessage(next);
      clearTimer.current = window.setTimeout(() => setMessage(""), 4000);
    });
  }, []);

  useEffect(() => {
    return () => {
      if (clearTimer.current) window.clearTimeout(clearTimer.current);
    };
  }, []);

  return { message, announce };
}
