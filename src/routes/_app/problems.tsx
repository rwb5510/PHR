import { createFileRoute } from "@tanstack/react-router";
import { ProblemsPage } from "@/components/chart-sections";

export const Route = createFileRoute("/_app/problems")({
  component: ProblemsPage,
});
