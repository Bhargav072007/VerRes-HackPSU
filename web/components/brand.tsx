// Vector mark plus the traced wordmark (currentColor, so it follows the theme). The name is carried by screen-reader text.
export function Brand() {
  return <span className="brand"><span className="brand-mark" aria-hidden="true" /><span className="brand-wordmark" aria-hidden="true" /><span className="sr-only">VerRes</span></span>;
}
