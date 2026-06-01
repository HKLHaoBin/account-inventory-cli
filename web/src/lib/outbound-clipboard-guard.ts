const STORAGE_KEY = "accountInventory.lastOutboundClipboardText";
const TTL_MS = 30_000;

type OutboundClipboardSnapshot = {
  normalizedText: string;
  expiresAt: number;
};

let pendingSnapshot: OutboundClipboardSnapshot | null = null;

function normalizeClipboardText(text: string): string {
  return text
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .join("\n");
}

function readStoredSnapshot(): OutboundClipboardSnapshot | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<OutboundClipboardSnapshot>;
    if (
      typeof value.normalizedText !== "string" ||
      typeof value.expiresAt !== "number"
    ) {
      return null;
    }
    return {
      normalizedText: value.normalizedText,
      expiresAt: value.expiresAt,
    };
  } catch {
    return null;
  }
}

export function clearOutboundClipboardText(): void {
  pendingSnapshot = null;
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Best-effort only; in-memory state still protects the current tab.
  }
}

export function rememberOutboundClipboardText(text: string): void {
  const normalizedText = normalizeClipboardText(text);
  if (!normalizedText) {
    clearOutboundClipboardText();
    return;
  }

  const snapshot = {
    normalizedText,
    expiresAt: Date.now() + TTL_MS,
  };
  pendingSnapshot = snapshot;

  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  } catch {
    // Best-effort only; in-memory state still protects the current tab.
  }
}

export function shouldIgnoreInboundClipboardText(text: string): boolean {
  const normalizedText = normalizeClipboardText(text);
  if (!normalizedText) return false;

  const snapshot = pendingSnapshot ?? readStoredSnapshot();
  if (!snapshot) return false;

  if (Date.now() > snapshot.expiresAt) {
    clearOutboundClipboardText();
    return false;
  }

  if (normalizedText !== snapshot.normalizedText) return false;

  clearOutboundClipboardText();
  return true;
}
