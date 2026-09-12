import { describe, expect, it } from "vitest";

import { resolveToolStatus } from "@/lib/toolStatus";
import { approvalTimeoutMs, approvalTimeoutSec } from "@/lib/approvalTimeout";

describe("resolveToolStatus", () => {
  it("treats explicit running as running even with a result", () => {
    expect(resolveToolStatus({ status: "running", result: { partial: true } })).toBe("running");
  });

  it("treats empty status without result as running", () => {
    expect(resolveToolStatus({ status: "" })).toBe("running");
    expect(resolveToolStatus({})).toBe("running");
  });

  it("treats empty status with result as done", () => {
    expect(resolveToolStatus({ status: "", result: { ok: 1 } })).toBe("done");
  });

  it("detects failed / stopped / done", () => {
    expect(resolveToolStatus({ status: "failed" })).toBe("failed");
    expect(resolveToolStatus({ success: false })).toBe("failed");
    expect(resolveToolStatus({ error: "boom" })).toBe("failed");
    expect(resolveToolStatus({ status: "stopped" })).toBe("stopped");
    expect(resolveToolStatus({ status: "ok" })).toBe("done");
    expect(resolveToolStatus({ success: true })).toBe("done");
  });
});

describe("approvalTimeoutMs", () => {
  it("uses graduated timeouts", () => {
    expect(approvalTimeoutSec("run_shell")).toBe(60);
    expect(approvalTimeoutSec("builtin_workspace_write_file")).toBe(45);
    expect(approvalTimeoutSec("edit_file")).toBe(45);
    expect(approvalTimeoutSec("read_file")).toBe(30);
    expect(approvalTimeoutMs("bash")).toBe(60_000);
  });
});
