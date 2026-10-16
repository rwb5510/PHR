import { createFileRoute } from "@tanstack/react-router";
import { ImmunizationsPage } from "@/components/chart-sections";

export const Route = createFileRoute("/_app/immunizations")({
  component: ImmunizationsPage,
});
