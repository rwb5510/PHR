import { createFileRoute } from "@tanstack/react-router";
import { ProceduresPage } from "@/components/chart-sections";

export const Route = createFileRoute("/_app/procedures")({
  component: ProceduresPage,
});
