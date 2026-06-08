export type ClipboardCopyResult =
  | { ok: true }
  | { ok: false; text: string; reason: string };

export class ClipboardCopyError extends Error {
  readonly text: string;

  readonly reason: string;

  constructor(text: string, reason: string) {
    super(reason);
    this.name = "ClipboardCopyError";
    this.text = text;
    this.reason = reason;
  }
}

function copyWithExecCommand(text: string): boolean {
  if (typeof document === "undefined" || typeof document.execCommand !== "function") {
    return false;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "0";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  textarea.setSelectionRange(0, text.length);

  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  } finally {
    document.body.removeChild(textarea);
  }

  return ok;
}

export async function copyToClipboard(text: string): Promise<ClipboardCopyResult> {
  const value = text ?? "";
  if (!value.trim()) {
    return { ok: false, text: value, reason: "没有可复制的内容" };
  }

  if (
    typeof navigator !== "undefined" &&
    navigator.clipboard &&
    typeof navigator.clipboard.writeText === "function"
  ) {
    try {
      await navigator.clipboard.writeText(value);
      return { ok: true };
    } catch {
      // Fall back to legacy copy below.
    }
  }

  if (copyWithExecCommand(value)) {
    return { ok: true };
  }

  return {
    ok: false,
    text: value,
    reason: "浏览器不允许自动复制，请手动复制",
  };
}

export function isClipboardCopyError(error: unknown): error is ClipboardCopyError {
  return error instanceof ClipboardCopyError;
}
