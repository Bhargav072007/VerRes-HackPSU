// Report-only styles consume the publisher tokens defined in app/globals.css.
export const reportTokens = `
.report-root,.report-overlay {
 --muted:var(--cloud);--border:var(--hairline);
 --verdict-SUPPORTED:#3F6B4F;--verdict-VERIFIED:#3F6B4F;--verdict-NONE:#3F6B4F;--verdict-PARTIALLY_SUPPORTED:#8A6B25;--verdict-NEEDS_REVIEW:#46677A;
 --foreground:var(--ink);--muted-foreground:var(--stone);--background:var(--snow);--primary:var(--graphite);--secondary:var(--cloud);--card:var(--surface);color:var(--ink);
}
.report-root {max-width:1280px!important;--reader-ink:var(--ink);--report-nav-bottom:0px;padding-top:0}
body:has(.report-root) > header {display:none}
.report-overlay.report-menu {box-shadow:var(--shadow-2)}
.report-root .report-card {border-radius:var(--radius-card);box-shadow:var(--shadow-1)}
.report-root .report-summary {border-radius:var(--radius-modal);box-shadow:var(--shadow-1)}
.report-root .check-row {}
.report-root [role=tab]::after {display:none}
.report-root .tab-indicator {position:absolute;bottom:-7px;left:8px;right:8px;height:2px;background:var(--ink)}
.report-root .reader-paragraph {position:relative;max-width:70ch;font-size:var(--reader-size,18px);line-height:var(--reader-leading,1.75);font-family:var(--reader-font,var(--font-source-serif));scroll-margin-top:250px}
.report-root .paragraph-number {position:absolute;right:calc(100% + 16px);top:6px;width:18px;white-space:nowrap;text-align:right;font:10px/2 var(--font-inter);color:var(--stone);user-select:none}
.report-root .cited-text {text-decoration-line:underline;text-decoration-color:#EB4603;text-decoration-thickness:2px;text-underline-offset:5px;text-decoration-skip-ink:none}
.report-root .citation-mark {scroll-margin-top:250px}
.report-root .citation-mark:hover {background:var(--cloud)}
.report-root .citation-preview {pointer-events:none;position:absolute;bottom:calc(100% + 10px);left:50%;transform:translateX(-50%);width:min(280px,70vw);padding:16px;border:1px solid var(--border);border-radius:6px;background:var(--surface);box-shadow:var(--shadow-2);font:12px/1.6 var(--font-inter);text-align:left;color:var(--ink);max-height:280px;overflow:hidden;opacity:0;visibility:hidden;z-index:25;}
.report-root .citation-mark:is(:hover,:focus-visible) .citation-preview {opacity:1;visibility:visible}
.report-root [data-flash=true] {}
.report-root .compact-header {position:fixed;inset:calc(var(--report-nav-bottom) + 12px) 24px auto;max-width:1104px;margin:auto;z-index:35;border:1px solid var(--border);border-radius:6px;background:var(--surface);box-shadow:var(--shadow-1);overflow:hidden;}
.report-root .report-floating-actions {position:fixed;top:calc(var(--report-nav-bottom) + 26px);right:max(48px,calc((100vw - 1104px)/2 + 24px));z-index:36}
.report-root .report-tabs {top:calc(var(--report-nav-bottom) + 12px)}
.report-root .report-tabs-compact {top:calc(var(--report-nav-bottom) + 88px)}
.report-overlay.evidence-panel {border-radius:var(--radius-modal) 0 0 var(--radius-modal);box-shadow:var(--shadow-3)}
.report-overlay.evidence-panel[data-state=closed] {}
.report-overlay.evidence-backdrop {background:#1b1b1926;backdrop-filter:blur(4px);}
.report-overlay.evidence-backdrop[data-state=closed] {}
.report-overlay .matched-span {background:var(--brass-tint);box-shadow:inset 0 -2px var(--brass);color:inherit}
.report-root .verdict-chip,.report-overlay .verdict-chip {}
.report-root .verdict-chip[data-critical=true],.report-overlay .verdict-chip[data-critical=true] {}
.report-root .xray-panel {border:1px solid var(--border);border-radius:6px;background:var(--snow);padding:16px}
.report-root .report-skeleton {position:relative;overflow:hidden;background:var(--cloud);border-radius:6px}
.report-root .report-skeleton::after {content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,#ffffffb3,transparent);transform:translateX(-100%)}
.report-root .review-receipts[open] > div {}
.report-root .graph-node {}
.report-root .graph-edge {}
.report-root .react-flow__attribution a {color:var(--muted-foreground)}
.report-root .report-graph [data-id] {}
.report-root .report-graph .react-flow__minimap {border:1px solid var(--border);border-radius:6px;box-shadow:var(--shadow-1)}
.report-root .report-graph .react-flow__minimap:not(:has(.react-flow__minimap-node)) {display:none}









@media(max-width:1279px) {.report-root .citation-preview {position:fixed;left:24px;right:24px;bottom:24px;width:auto;max-width:32rem;margin:auto;transform:none}}
@media(max-width:639px) {
 .report-overlay.evidence-panel {border-radius:0;}
 .report-root {--report-nav-bottom:0px;padding-top:0}
 .report-root .compact-header {left:12px;right:12px}
 .report-root .report-floating-actions {right:28px}
 .report-root .paragraph-number {right:calc(100% + 10px)}
}
@media(prefers-reduced-motion:reduce) {.report-root *,.report-root *::after,.report-overlay * {scroll-behavior:auto!important}}
html[data-a11y-motion=reduce] :is(.report-root,.report-overlay) *,html[data-a11y-motion=reduce] .report-root *::after {scroll-behavior:auto!important}
`;
