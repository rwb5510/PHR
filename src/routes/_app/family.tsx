import { createFileRoute } from "@tanstack/react-router";
import { FamilyPage } from "@/components/chart-sections";

export const Route = createFileRoute("/_app/family")({
  component: FamilyPage,
});
