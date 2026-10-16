import { createFileRoute, Outlet } from "@tanstack/react-router";
import { ChartShell } from "@/components/chart-shell";

export const Route = createFileRoute("/_app")({
  component: () => (
    <ChartShell>
      <Outlet />
    </ChartShell>
  ),
});
