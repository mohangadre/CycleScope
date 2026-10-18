import { Dashboard } from "@/components/Dashboard";
import { configuredAsOf, configuredStart } from "@/lib/startup";

export const dynamic = "force-dynamic";

export default function Page() {
  return <Dashboard defaultAsOf={configuredAsOf()} defaultStart={configuredStart()} />;
}
