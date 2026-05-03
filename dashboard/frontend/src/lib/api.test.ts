import { afterEach, describe, expect, it } from "vitest";
import {
  getActiveRunId,
  getActiveUserId,
  setActiveRunId,
  setActiveUserId,
} from "./api";

describe("api module-level run/user id store", () => {
  afterEach(() => {
    setActiveRunId(null);
    setActiveUserId(null);
  });

  it("starts with no active run id", () => {
    expect(getActiveRunId()).toBeNull();
  });

  it("round-trips a run id through the setter", () => {
    setActiveRunId("run_abc123");
    expect(getActiveRunId()).toBe("run_abc123");
  });

  it("clears the run id when set to null", () => {
    setActiveRunId("run_abc123");
    setActiveRunId(null);
    expect(getActiveRunId()).toBeNull();
  });

  it("round-trips a user id through the setter", () => {
    setActiveUserId("user_42");
    expect(getActiveUserId()).toBe("user_42");
  });

  it("keeps run id and user id independent", () => {
    setActiveRunId("run_xyz");
    setActiveUserId("user_42");
    expect(getActiveRunId()).toBe("run_xyz");
    expect(getActiveUserId()).toBe("user_42");

    setActiveRunId(null);
    expect(getActiveRunId()).toBeNull();
    expect(getActiveUserId()).toBe("user_42");
  });
});
