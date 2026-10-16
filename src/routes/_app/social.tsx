import { createFileRoute } from "@tanstack/react-router";
import { SocialPage } from "@/components/chart-sections";

export const Route = createFileRoute("/_app/social")({
  component: SocialPage,
});
