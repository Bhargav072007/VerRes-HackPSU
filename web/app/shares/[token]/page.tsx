import { ReportReader } from "@/components/report-reader";

export default async function SharedReportPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <ReportReader key={token} id={token} shared />;
}
