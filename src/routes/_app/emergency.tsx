import { createFileRoute } from "@tanstack/react-router";
import { EmergencyPage } from "@/components/chart-sections";

export const Route = createFileRoute("/_app/emergency")({
  component: EmergencyPage,
});
