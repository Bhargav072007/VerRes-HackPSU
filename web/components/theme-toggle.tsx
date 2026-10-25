"use client";
import { useSyncExternalStore } from "react";
import { Moon, Sun } from "lucide-react";
import { setThemeChoice } from "@/lib/theme";
const subscribe = (update: () => void) => { const observer = new MutationObserver(update); observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] }); return () => observer.disconnect(); };
// Sun/moon switch for the whole site; it writes the shared theme choice that reader settings also use.
export function ThemeToggle() {
  const dark = useSyncExternalStore(subscribe, () => document.documentElement.dataset.theme === "dark", () => false);
  return <button type="button" className="theme-toggle" aria-label={dark ? "Switch to light theme" : "Switch to dark theme"} onClick={() => setThemeChoice(dark ? "light" : "dark")}>{dark ? <Sun size={18} aria-hidden /> : <Moon size={18} aria-hidden />}</button>;
}
