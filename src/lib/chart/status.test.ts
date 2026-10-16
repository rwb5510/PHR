import assert from "node:assert/strict";
import test from "node:test";
import { isListed } from "./status.ts";

test("voided rows are hidden until asked for", () => {
  assert.equal(isListed("entered_in_error", false), false);
  assert.equal(isListed("entered_in_error", true), true);
});

test("resolved, stopped, and held rows stay on the list", () => {
  for (const status of ["active", "resolved", "stopped", "held"]) {
    assert.equal(isListed(status, false), true);
  }
});
