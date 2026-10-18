import { SectorDashboard } from "@/components/SectorDashboard";
import { configuredAsOf } from "@/lib/startup";

export const dynamic = "force-dynamic";

export default function SectorsPage() {
  return <SectorDashboard defaultAsOf={configuredAsOf()} />;
}
