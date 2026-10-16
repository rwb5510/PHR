import { createFileRoute } from "@tanstack/react-router";
import { AllergiesPage } from "@/components/chart-sections";

export const Route = createFileRoute("/_app/allergies")({
  component: AllergiesPage,
});
