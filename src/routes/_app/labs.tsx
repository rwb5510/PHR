import { createFileRoute } from "@tanstack/react-router";
import { LaterPhase } from "@/components/later-phase";

export const Route = createFileRoute("/_app/labs")({
  component: () => <LaterPhase title="Labs" />,
});
