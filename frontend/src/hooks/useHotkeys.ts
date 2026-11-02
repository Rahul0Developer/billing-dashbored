// ---- Global keyboard shortcut manager ----
import { useEffect } from "react";

type Handler = (e: KeyboardEvent) => void;

/**
 * Registers keydown handlers by combo string, e.g. "F2", "ctrl+k", "delete".
 * Ignores events typed into inputs/textareas except for F-keys and Escape,
 * so the barcode scanner wedge keeps working inside the search box.
 */
export function useHotkeys(map: Record<string, Handler>, deps: unknown[] = []): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = !!target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      const key = e.key.toLowerCase();
      const combo = (e.ctrlKey || e.metaKey ? "ctrl+" : "") + key;
      const handler = map[combo] ?? map[e.key];
      if (!handler) return;
      const isFunctionKey = key.startsWith("f") && key.length <= 3;
      if (typing && !isFunctionKey && key !== "escape") return;
      handler(e);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
