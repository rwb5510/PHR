/** Voided rows stay out of the default list. Resolved, stopped, and held stay visible. */
export function isListed(status: string, showVoided: boolean): boolean {
  if (status === "entered_in_error") return showVoided;
  return true;
}
