import { createFileRoute } from "@tanstack/react-router";
import { ContactsPage } from "@/components/chart-sections";

export const Route = createFileRoute("/_app/contacts")({
  component: ContactsPage,
});
