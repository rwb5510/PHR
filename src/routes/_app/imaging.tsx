import { createFileRoute } from "@tanstack/react-router";
import { LaterPhase } from "@/components/later-phase";

export const Route = createFileRoute("/_app/imaging")({
  component: () => <LaterPhase title="Imaging" />,
});
