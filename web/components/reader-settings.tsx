"use client";
import { createContext, useContext, useEffect, useState, useRef } from "react";
import { usePathname } from "next/navigation";
import { Popover } from "radix-ui";
import { X } from "lucide-react";
import { parseReaderSettings, readerDefaults, type ReaderSettings } from "@/lib/reader-settings";
const Context = createContext<{ settings: ReaderSettings; update: (value: Partial<ReaderSettings>) => void }>({ settings: readerDefaults, update: () => {} });
export function ReaderPreferences({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = useState<ReaderSettings>(readerDefaults), [ready, setReady] = useState(false);
  const pathname = usePathname();
  const applied = useRef(false);
  useEffect(() => {
    let saved: ReaderSettings = readerDefaults;
    try { saved = parseReaderSettings(JSON.parse(localStorage.getItem("verres-reader") || "null")); } catch { /* Storage is optional. */ }
    const frame = requestAnimationFrame(() => { setSettings(saved); setReady(true); });
    return () => cancelAnimationFrame(frame);
  }, []);
  useEffect(() => {
    if (!ready) return;
    const root = document.documentElement;
    const reading = pathname.startsWith("/report/") || pathname.startsWith("/shares/");
    root.dataset.readerTheme = reading ? settings.theme : "light";
    root.dataset.readerWidth = settings.width;
    root.style.setProperty("--reader-size", `${settings.size}px`);
    root.style.setProperty("--reader-leading", String({ compact: 1.5, comfortable: 1.75, open: 2 }[settings.spacing]));
    root.style.setProperty("--reader-font", settings.font === "sans" ? "var(--font-inter)" : "var(--font-source-serif)");
    if (settings.reduceMotion || applied.current || root.dataset.a11yMotion !== "reduce") root.dataset.a11yMotion = settings.reduceMotion ? "reduce" : "system";
    applied.current = true;
    try { localStorage.setItem("verres-reader", JSON.stringify(settings)); } catch { /* Private browsing can disable storage. */ }
  }, [settings, ready, pathname]);
  return <Context.Provider value={{ settings, update: value => setSettings(current => ({ ...current, ...value })) }}>{children}</Context.Provider>;
}
export function ReaderSettingsButton() {
  const { settings, update } = useContext(Context);
  return <Popover.Root><Popover.Trigger className="reader-settings-trigger" aria-label="Reader settings">Aa</Popover.Trigger><Popover.Portal><Popover.Content className="report-overlay reader-settings" align="end" sideOffset={10} collisionPadding={12} aria-label="Reader settings"><div className="flex items-center justify-between"><h2 className="text-sm font-medium">Reader settings</h2><Popover.Close aria-label="Close reader settings"><X size={16} /></Popover.Close></div><label className="settings-size">Text size <output>{settings.size}px</output><input aria-label="Text size" type="range" min="14" max="22" step="1" value={settings.size} onChange={e => update({ size: Number(e.target.value) })} /></label>{([['spacing', 'Line spacing', ['compact', 'comfortable', 'open']], ['theme', 'Theme', ['light', 'sepia', 'dark']], ['width', 'Reading width', ['narrow', 'standard', 'wide']], ['font', 'Paper font', ['serif', 'sans']]] as const).map(([key, label, options]) => <fieldset key={key}><legend>{label}</legend><div className="settings-options">{options.map(value => <button type="button" key={value} data-setting={value} aria-pressed={settings[key] === value} onClick={() => update({ [key]: value })}>{value}</button>)}</div></fieldset>)}<label className="settings-motion"><input type="checkbox" checked={settings.reduceMotion} onChange={e => update({ reduceMotion: e.target.checked })} /> Reduce motion</label></Popover.Content></Popover.Portal></Popover.Root>;
}
