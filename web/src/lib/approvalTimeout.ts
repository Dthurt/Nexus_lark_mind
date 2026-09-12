/** Shared approval countdown — keep UI + timeline in sync. */

export const APPROVAL_TIMEOUT_DEFAULT_MS = 30_000;
export const APPROVAL_TIMEOUT_SHELL_MS = 60_000;
export const APPROVAL_TIMEOUT_WRITE_MS = 45_000;

/** Graduated timeouts: shell / edits need more reading time than simple tools. */
export function approvalTimeoutMs(baseOrName?: string | null): number {
  const b = String(baseOrName || "")
    .trim()
    .toLowerCase();
  const leaf = b.includes(".") ? b.split(".").pop()! : b;
  const short = leaf
    .replace(/^builtin_workspace_/, "")
    .replace(/^builtin_/, "")
    .replace(/^cli_/, "");

  if (
    short === "run_shell" ||
    short === "bash" ||
    short === "shell" ||
    short === "terminal" ||
    short === "exec"
  ) {
    return APPROVAL_TIMEOUT_SHELL_MS;
  }
  if (
    short === "write_file" ||
    short === "edit_file" ||
    short === "apply_patch" ||
    short === "str_replace" ||
    short === "create_file"
  ) {
    return APPROVAL_TIMEOUT_WRITE_MS;
  }
  return APPROVAL_TIMEOUT_DEFAULT_MS;
}

export function approvalTimeoutSec(baseOrName?: string | null): number {
  return Math.round(approvalTimeoutMs(baseOrName) / 1000);
}
