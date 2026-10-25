import assert from "node:assert/strict";
import { test } from "node:test";
import { isReadingPath, resolveTheme, themeScript } from "../lib/theme";

test("theme resolves from the stored choice, else the system preference", () => {
  assert.equal(resolveTheme("dark", false), "dark");
  assert.equal(resolveTheme("light", true), "light");
  assert.equal(resolveTheme("sepia", true), "light");
  assert.equal(resolveTheme(null, true), "dark");
  assert.equal(resolveTheme(null, false), "light");
  assert.equal(isReadingPath("/report/x"), true);
  assert.equal(isReadingPath("/check/x"), false);
});

test("the pre-paint script applies the same rules and survives blocked storage", () => {
  const run = (stored: string | null, dark: boolean, path: string, blocked = false) => {
    const dataset: Record<string, string> = {};
    const scope = { localStorage: { getItem: () => { if (blocked) throw new Error("blocked"); return stored; } }, window: { matchMedia: true }, matchMedia: () => ({ matches: dark }), document: { documentElement: { dataset } }, location: { pathname: path } };
    new Function(...Object.keys(scope), themeScript)(...Object.values(scope));
    return dataset;
  };
  assert.deepEqual(run("dark", false, "/"), { theme: "dark", themeChoice: "dark", readerTheme: "dark" });
  assert.deepEqual(run("sepia", true, "/report/a"), { theme: "light", themeChoice: "sepia", readerTheme: "sepia" });
  assert.deepEqual(run(null, true, "/", true), { theme: "dark", themeChoice: "system", readerTheme: "dark" });
  assert.deepEqual(run("bogus", false, "/"), { theme: "light", themeChoice: "system", readerTheme: "light" });
});
