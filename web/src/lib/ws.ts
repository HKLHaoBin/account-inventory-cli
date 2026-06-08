import type { ClipboardMessage } from "@/types/account";

export function getClipboardWsUrl(): string {
  if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL;
  if (typeof window === "undefined") return "ws://127.0.0.1:8000/ws/clipboard";
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/clipboard`;
}

export function isClipboardMessage(value: unknown): value is ClipboardMessage {
  if (!value || typeof value !== "object") return false;
  const message = value as Partial<ClipboardMessage>;
  return message.source === "clipboard" && typeof message.text === "string";
}

export function clipboardLoadedStatus(text: string): string {
  const lineCount = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean).length;
  return `已从剪贴板载入 ${lineCount} 行`;
}
