import { createFileRoute } from "@tanstack/react-router";
import { AppointmentsPage } from "@/components/chart-sections";

export const Route = createFileRoute("/_app/appointments")({
  component: AppointmentsPage,
});
