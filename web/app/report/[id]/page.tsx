import { ReportReader } from "@/components/report-reader";

export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReportReader key={id} id={id} />;
}
