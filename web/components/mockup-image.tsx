import { Reveal } from "./editorial-motion";
import Image, { type ImageLoaderProps } from "next/image";
// Both sizes are encoded offline by composite.py; avoid first-request AVIF encoding.
const mockupLoader = ({ src, width }: ImageLoaderProps) => src.replace("@2x", width <= 768 ? "@1x" : "@2x");
import manifest from "@/public/mockups/manifest.json";
export function MockupImage({ scene, alt, priority = false, sizes = "(max-width: 700px) 100vw, 60vw" }: { scene: keyof typeof manifest; alt: string; priority?: boolean; sizes?: string }) {
 const meta = manifest[scene];
 const image = <Image loader={mockupLoader} className="mockup-image" src={`/mockups/${scene}@2x.avif`} width={meta.width} height={meta.height} alt={alt} priority={priority} fetchPriority={priority ? "high" : undefined} sizes={sizes} placeholder={priority ? "empty" : "blur"} blurDataURL={meta.blurDataURL} />;
 return priority || scene === "s5" ? image : <Reveal image>{image}</Reveal>;
}
