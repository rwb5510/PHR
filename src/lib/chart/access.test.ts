import assert from "node:assert/strict";
import test from "node:test";
import { assertSameHousehold, profileBelongsToHousehold } from "./access.ts";

test("a profile in the same household is visible", () => {
  assert.equal(profileBelongsToHousehold("house-a", "house-a"), true);
  assert.doesNotThrow(() => assertSameHousehold("house-a", "house-a"));
});

test("another household looks the same as a missing profile", () => {
  assert.equal(profileBelongsToHousehold("house-b", "house-a"), false);
  assert.throws(() => assertSameHousehold("house-b", "house-a"), { message: "Not found" });
  assert.throws(() => assertSameHousehold(null, "house-a"), { message: "Not found" });
});
