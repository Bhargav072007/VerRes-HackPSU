import Image from "next/image";
import manifest from "@/public/mockups/manifest.json";
export function MockupImage({ scene, alt, priority = false, sizes = "(max-width: 700px) 100vw, 60vw" }: { scene: keyof typeof manifest; alt: string; priority?: boolean; sizes?: string }) {
 const meta = manifest[scene];
 return <Image className="mockup-image" src={`/mockups/${scene}@2x.avif`} width={meta.width} height={meta.height} alt={alt} priority={priority} sizes={sizes} placeholder="blur" blurDataURL={meta.blurDataURL} />;
}
