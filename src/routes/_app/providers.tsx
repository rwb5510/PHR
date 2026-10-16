import { createFileRoute } from "@tanstack/react-router";
import { ProvidersPage } from "@/components/chart-sections";

export const Route = createFileRoute("/_app/providers")({
  component: ProvidersPage,
});
