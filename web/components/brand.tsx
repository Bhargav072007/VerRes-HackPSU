import Image from "next/image";
export function Brand({ lockup = false }: { lockup?: boolean }) {
  return lockup ? <Image className="brand-lockup" src="/brand/verres-lockup.png" alt="VerRes" width={300} height={217} /> : <span className="brand"><span className="brand-mark" aria-hidden="true" /><span>VerRes</span></span>;
}
