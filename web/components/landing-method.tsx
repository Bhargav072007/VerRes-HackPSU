"use client";
import { useState } from "react";
import Image from "next/image";
const methods = [
 ["Exists", "Resolve the reference through Crossref, OpenAlex, and arXiv.", "exists"],
 ["Matches its DOI", "Compare the identifier with the cited bibliographic record.", "doi"],
 ["Not retracted", "Follow a retraction finding back to the linked notice.", "retraction"],
 ["Actually says it", "Read the verified source passage beside the claim.", "evidence"],
 ["No hidden prompts", "Inspect concealed or instruction-like manuscript text.", "hidden"],
 ["Survives peer review", "Read three reviewer perspectives and the area chair’s priorities.", "review"],
] as const;
function MethodShot({ index }: { index: number }) { return <Image src={`/mockups/method-${methods[index][2]}.webp`} alt={`Recorded ${methods[index][0].toLowerCase()} check`} width={1200} height={900} sizes="(max-width: 700px) 90vw, 55vw" />; }
export function LandingMethod() {
 const [active, setActive] = useState(0);
 return <section id="how-it-works" className="article-section section-container"><h2 className="editorial-title">Every citation, <strong>checked.</strong></h2><div className="method-layout"><ol className="method-list">{methods.map(([title,description], i) => <li key={title}><button aria-pressed={active === i} onMouseEnter={() => setActive(i)} onFocus={() => setActive(i)} onClick={() => setActive(i)}><span>{String(i+1).padStart(2,"0")}</span><div><h3>{title}</h3><p>{description}</p></div></button></li>)}</ol><div className="method-panel"><MethodShot index={active} /></div></div><div className="method-accordion">{methods.map(([title,description],i) => <details key={title} name="methods"><summary>{String(i+1).padStart(2,"0")} · {title}</summary><p>{description}</p><MethodShot index={i} /></details>)}</div></section>;
}
