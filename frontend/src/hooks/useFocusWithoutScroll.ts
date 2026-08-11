import { useEffect, useRef } from "react";

/** Focus an input when `active` without scrolling the page (portal / autoFocus fix). */
export function useFocusWithoutScroll<T extends HTMLElement>(active: boolean) {
  const ref = useRef<T>(null);

  useEffect(() => {
    if (!active) return;
    const el = ref.current;
    if (!el) return;

    const frame = requestAnimationFrame(() => {
      el.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [active]);

  return ref;
}
