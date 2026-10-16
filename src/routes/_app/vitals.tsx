import { createFileRoute } from "@tanstack/react-router";
import { VitalsPage } from "@/components/chart-sections";

export const Route = createFileRoute("/_app/vitals")({
  component: VitalsPage,
});
