// One theme for the whole site. The choice lives in localStorage ("verres-theme"); no choice means "follow the system".
// Sepia is a reading-only variant of light, applied on report pages through data-reader-theme.
export type ThemeChoice = "light" | "dark" | "sepia";
export const THEME_KEY = "verres-theme", THEME_EVENT = "verres-theme";
const valid = (v: unknown): v is ThemeChoice => v === "light" || v === "dark" || v === "sepia";
export function readThemeChoice(): ThemeChoice | null { try { const v = localStorage.getItem(THEME_KEY); return valid(v) ? v : null; } catch { return null; } }
export const systemPrefersDark = () => typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches;
export function resolveTheme(choice: ThemeChoice | null, prefersDark: boolean): "light" | "dark" { return choice === "dark" || (choice === null && prefersDark) ? "dark" : "light"; }
export const isReadingPath = (path: string) => path.startsWith("/report/") || path.startsWith("/shares/");
export function applyTheme(choice: ThemeChoice | null) {
  const root = document.documentElement, theme = resolveTheme(choice, systemPrefersDark());
  root.dataset.theme = theme; root.dataset.themeChoice = choice ?? "system";
  root.dataset.readerTheme = isReadingPath(location.pathname) ? (choice === "sepia" ? "sepia" : theme) : theme;
}
export function setThemeChoice(choice: ThemeChoice) {
  try { localStorage.setItem(THEME_KEY, choice); } catch { /* The choice still applies for this page view. */ }
  applyTheme(choice); dispatchEvent(new CustomEvent<ThemeChoice>(THEME_EVENT, { detail: choice }));
}
// Inline before paint (layout.tsx), so a stored or system dark theme never flashes light.
export const themeScript = `(function(){var c=null;try{c=localStorage.getItem("${THEME_KEY}")}catch(e){}if(c!=="light"&&c!=="dark"&&c!=="sepia")c=null;var d=c==="dark"||(c===null&&window.matchMedia&&matchMedia("(prefers-color-scheme: dark)").matches),t=d?"dark":"light",r=document.documentElement,p=location.pathname,reading=p.indexOf("/report/")===0||p.indexOf("/shares/")===0;r.dataset.theme=t;r.dataset.themeChoice=c||"system";r.dataset.readerTheme=reading&&c==="sepia"?"sepia":t})()`;
