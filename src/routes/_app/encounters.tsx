import { createFileRoute } from "@tanstack/react-router";
import { EncountersPage } from "@/components/chart-sections";

export const Route = createFileRoute("/_app/encounters")({
  component: EncountersPage,
});
