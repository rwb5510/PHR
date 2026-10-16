import { createFileRoute } from "@tanstack/react-router";
import { PharmacyPage } from "@/components/chart-sections";

export const Route = createFileRoute("/_app/pharmacy")({
  component: PharmacyPage,
});
