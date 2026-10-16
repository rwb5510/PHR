/** True when a profile row is in the caller's household. */
export function profileBelongsToHousehold(
  profileHouseholdId: string,
  callerHouseholdId: string,
): boolean {
  return profileHouseholdId.length > 0 && profileHouseholdId === callerHouseholdId;
}

/** One error for a missing profile and for someone else's household. */
export function assertSameHousehold(
  profileHouseholdId: string | null | undefined,
  callerHouseholdId: string,
): void {
  if (!profileHouseholdId || !profileBelongsToHousehold(profileHouseholdId, callerHouseholdId)) {
    throw new Error("Not found");
  }
}
