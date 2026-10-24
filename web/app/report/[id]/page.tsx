import { LiveCheck } from "@/components/live-check";

// Keep receipts accessible until the full report UI lands.
export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  return <LiveCheck id={(await params).id} report />;
}
