// Bridges the imperative API client (no React context there) to React UI.
import React from "react";
import { ToastProvider } from "./components/ui";
import { onUnauthorized } from "./api/client";

export { ToastProvider };

let logoutHook: (() => void) | null = null;
export function onUnauthorizedBridge(fn: () => void): () => void {
  logoutHook = fn;
  return onUnauthorized(() => logoutHook?.());
}
