import { createFileRoute } from "@tanstack/react-router";
import { InsurancePage } from "@/components/chart-sections";

export const Route = createFileRoute("/_app/insurance")({
  component: InsurancePage,
});
