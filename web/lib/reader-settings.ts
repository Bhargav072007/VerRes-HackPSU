export const readerDefaults = { size: 18, spacing: "comfortable", theme: "light", width: "standard", font: "serif", reduceMotion: false } as const;
export type ReaderSettings = { size: number; spacing: "compact" | "comfortable" | "open"; theme: "light" | "sepia" | "dark"; width: "narrow" | "standard" | "wide"; font: "serif" | "sans"; reduceMotion: boolean };
export function parseReaderSettings(value: unknown): ReaderSettings {
  const v = value && typeof value === "object" ? value as Record<string, unknown> : {};
  return { size: typeof v.size === "number" && Number.isFinite(v.size) ? Math.max(14, Math.min(22, v.size)) : 18,
    spacing: v.spacing === "compact" || v.spacing === "open" ? v.spacing : "comfortable",
    theme: v.theme === "sepia" || v.theme === "dark" ? v.theme : "light",
    width: v.width === "narrow" || v.width === "wide" ? v.width : "standard",
    font: v.font === "sans" ? "sans" : "serif", reduceMotion: v.reduceMotion === true };
}
