import { createFileRoute } from "@tanstack/react-router";
import { MedicationsPage } from "@/components/chart-sections";

export const Route = createFileRoute("/_app/medications")({
  component: MedicationsPage,
});
