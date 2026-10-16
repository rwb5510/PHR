import { createFileRoute } from "@tanstack/react-router";
import { ImplantsPage } from "@/components/chart-sections";

export const Route = createFileRoute("/_app/implants")({
  component: ImplantsPage,
});
