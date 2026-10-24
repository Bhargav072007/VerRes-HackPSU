import { LiveCheck } from "@/components/live-check";

export default async function CheckPage({ params }: { params: Promise<{ id: string }> }) {
  return <LiveCheck id={(await params).id} />;
}
