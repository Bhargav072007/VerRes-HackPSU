// Temporary report scope; names and values match DESIGN_SPEC sections 1–2.
export const reportTokens = `
.report-root,.report-overlay {
 --snow:#f6f6f5;--surface:#ffffff;--ink:#1b1b19;--graphite:#3a3a38;--inkwell:#3a3a38;--stone:#706f6c;--muted:#ececea;--fog:#9c9b98;--cloud:#ececea;
 --hairline:rgba(0,0,0,.08);--border:var(--hairline);--border-strong:rgba(0,0,0,.12);--divider:rgba(0,0,0,.06);
 --brass:#c49a3c;--brass-text:#8a6b25;--brass-tint:#fbf5e6;--sage:#7a9b87;--sage-text:#4e6b5c;--sage-tint:#edf4f0;--red:#b42318;--red-tint:#fef3f2;--blue-ink:#46677a;--blue-tint:#ebf2f6;
 --verdict-SUPPORTED:var(--sage-text);--verdict-VERIFIED:var(--sage-text);--verdict-NONE:var(--sage-text);--verdict-PARTIALLY_SUPPORTED:var(--brass-text);--verdict-NEEDS_REVIEW:var(--blue-ink);
 --radius-button:12px;--radius-input:10px;--radius-card:16px;--radius-modal:20px;--radius-pill:9999px;
 --space-1:4px;--space-2:8px;--space-3:12px;--space-4:16px;--space-6:24px;--space-8:32px;--space-12:48px;
 --shadow-1:0 8px 24px #1b1b1912,0 1px 2px #1b1b190a;--shadow-2:0 18px 48px #1b1b1914,0 2px 8px #1b1b190a;--shadow-3:0 26px 80px #1b1b191a,0 4px 14px #1b1b190d;
 --motion-fast:.14s;--motion-base:.22s;--motion-slow:.36s;--ease-standard:cubic-bezier(.2,0,0,1);--ease-out-soft:cubic-bezier(.2,.7,.2,1);
 --foreground:var(--ink);--muted-foreground:#686762;--background:var(--snow);--primary:var(--graphite);--secondary:var(--cloud);--card:var(--surface);color:var(--ink);
}
.report-root {max-width:1280px!important;--reader-ink:var(--ink)}
.report-overlay.report-menu {animation:drop-in var(--motion-fast) var(--ease-standard);box-shadow:var(--shadow-2)}
.report-root .report-card {border-radius:var(--radius-card);box-shadow:var(--shadow-1)}
.report-root .report-summary {border-radius:var(--radius-modal);box-shadow:var(--shadow-1)}
.report-root .stat-tile {animation:settle var(--motion-base) var(--ease-out-soft) both}
.report-root .check-row {animation:msg-in var(--motion-base) var(--ease-out-soft) both}
.report-root [role=tab]::after {display:none}
.report-root .tab-indicator {position:absolute;bottom:-7px;left:8px;right:8px;height:2px;background:var(--ink)}
.report-root .reader-paragraph {position:relative;max-width:70ch;font-size:18px;line-height:1.75;scroll-margin-top:112px}
.report-root .paragraph-number {position:absolute;right:calc(100% + 16px);top:6px;width:18px;white-space:nowrap;text-align:right;font:10px/2 var(--font-inter);color:var(--stone);user-select:none}
.report-root .cited-text {text-decoration-line:underline;text-decoration-color:var(--verdict-color);text-decoration-thickness:2px;text-underline-offset:5px;text-decoration-skip-ink:none}
.report-root .citation-mark {scroll-margin-top:112px}
.report-root .citation-mark:hover {background:var(--cloud)}
.report-root .citation-preview {pointer-events:none;position:absolute;bottom:calc(100% + 10px);left:50%;transform:translateX(-50%);width:min(280px,70vw);padding:16px;border:1px solid var(--border);border-radius:12px;background:white;box-shadow:var(--shadow-2);font:12px/1.6 var(--font-inter);text-align:left;color:var(--ink);max-height:280px;overflow:hidden;opacity:0;visibility:hidden;z-index:25;transition:opacity var(--motion-fast)}
.report-root .citation-mark:is(:hover,:focus-visible) .citation-preview {opacity:1;visibility:visible}
.report-root [data-flash=true] {animation:cl-flash 1s var(--ease-out-soft)}
.report-root .compact-header {position:fixed;inset:12px 24px auto;max-width:1104px;margin:auto;z-index:35;border:1px solid var(--border);border-radius:9999px;background:#fffffff5;box-shadow:var(--shadow-1);overflow:hidden;transition:transform var(--motion-base) var(--ease-standard),opacity var(--motion-base) var(--ease-standard)}
.report-root .report-floating-actions {position:fixed;top:26px;right:max(48px,calc((100vw - 1104px)/2 + 24px));z-index:40}
.report-root .read-progress {position:absolute;bottom:0;left:0;right:0;height:2px;background:var(--graphite);transform-origin:left}
.report-overlay.evidence-panel {animation:panel-in .2s var(--ease-standard);border-radius:var(--radius-modal) 0 0 var(--radius-modal);box-shadow:var(--shadow-3)}
.report-overlay.evidence-panel[data-state=closed] {animation:panel-out .14s var(--ease-standard) forwards}
.report-overlay.evidence-backdrop {background:#1b1b1926;backdrop-filter:blur(4px);animation:report-fade .2s var(--ease-standard)}
.report-overlay.evidence-backdrop[data-state=closed] {animation:report-fade .14s reverse forwards}
.report-overlay .matched-span {background:var(--brass-tint);box-shadow:inset 0 -2px var(--brass);color:inherit}
.report-root .verdict-chip,.report-overlay .verdict-chip {animation:chip-in var(--motion-base) var(--ease-out-soft)}
.report-root .verdict-chip[data-critical=true],.report-overlay .verdict-chip[data-critical=true] {animation:msg-in var(--motion-fast) var(--ease-standard)}
.report-root .xray-panel {border:1px solid var(--border);border-radius:10px;background:repeating-linear-gradient(0deg,#1b1b1903 0px,#1b1b1903 1px,transparent 1px,transparent 4px),var(--snow);padding:16px}
.report-root .report-skeleton {position:relative;overflow:hidden;background:var(--cloud);border-radius:8px}
.report-root .report-skeleton::after {content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,#ffffffb3,transparent);animation:report-shimmer 1.4s infinite;transform:translateX(-100%)}
.report-root .review-receipts[open] > div {animation:msg-in var(--motion-base) var(--ease-out-soft)}
.report-root .graph-node {animation:settle var(--motion-slow) var(--ease-out-soft) both}
.report-root .graph-edge {animation:report-edge .36s var(--ease-standard) both}
.report-root .react-flow__attribution a {color:var(--muted-foreground)}
.report-root .report-graph [data-id] {transition:opacity var(--motion-fast)}
.report-root .report-graph .react-flow__minimap {border:1px solid var(--border);border-radius:10px;box-shadow:var(--shadow-1)}
@keyframes settle {from {opacity:0;transform:scale(.985)}to {opacity:1;transform:none}}
@keyframes msg-in {from {opacity:0;transform:translateY(8px)}to {opacity:1;transform:none}}
@keyframes page-in {from {opacity:0;transform:translateY(6px)}to {opacity:1;transform:none}}
@keyframes drop-in {from {opacity:0;transform:translateY(-4px) scale(.98)}to {opacity:1;transform:none}}
@keyframes panel-in {from {opacity:0;transform:translateX(16px)}to {opacity:1;transform:none}}
@keyframes panel-out {to {opacity:0;transform:translateX(16px)}}
@keyframes modal-in {from {opacity:0;transform:translateY(8px)}to {opacity:1;transform:none}}
@keyframes chip-in {0% {opacity:0;transform:scale(.9)}65% {transform:scale(1.06)}100% {opacity:1;transform:none}}
@keyframes cl-flash {from {background-color:var(--brass-tint)}to {background-color:transparent}}
@keyframes report-fade {from {opacity:0}to {opacity:1}}
@keyframes report-shimmer {to {transform:translateX(100%)}}
@keyframes report-edge {from {stroke-dashoffset:1}to {stroke-dashoffset:0}}
@media(max-width:1279px) {.report-root .citation-preview {position:fixed;left:24px;right:24px;bottom:24px;width:auto;max-width:32rem;margin:auto;transform:none}}
@media(max-width:639px) {
 .report-overlay.evidence-panel {border-radius:0;animation-name:modal-in}
 .report-root .compact-header {inset:8px 12px auto}
 .report-root .report-floating-actions {top:22px;right:28px}
 .report-root .paragraph-number {right:calc(100% + 10px)}
}
@media(prefers-reduced-motion:reduce) {.report-root *,.report-root *::after,.report-overlay * {animation:none!important;transition:none!important;scroll-behavior:auto!important}}
html[data-a11y-motion=reduce] :is(.report-root,.report-overlay) *,html[data-a11y-motion=reduce] .report-root *::after {animation:none!important;transition:none!important;scroll-behavior:auto!important}
`;
