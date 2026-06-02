import type {
  Account,
  DatabaseInfo,
  DatabaseListPayload,
  DashboardPayload,
  FifoCommitPayload,
  FifoPreviewPayload,
  InboundCommitPayload,
  InboundPreviewRow,
  InventoryPayload,
  OutboundByUsernamePayload,
  OutboundHistoryPayload,
  OutboundRecord,
  OutboundPasteCommitPayload,
  OutboundPasteRow,
  SearchPayload,
  SearchResult,
  UpdateStatusPayload,
} from "@/types/account";
import {
  clearOutboundClipboardText,
  rememberOutboundClipboardText,
} from "@/lib/outbound-clipboard-guard";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

async function requestJson<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `请求失败：${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function fetchDashboard(): Promise<DashboardPayload> {
  return requestJson<DashboardPayload>("/api/dashboard");
}

export function fetchDatabases(): Promise<DatabaseListPayload> {
  return requestJson<DatabaseListPayload>("/api/databases");
}

export function createDatabase(name: string): Promise<DatabaseInfo> {
  return requestJson<DatabaseInfo>("/api/databases", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function cloneDatabase(
  databaseId: string,
  name: string
): Promise<DatabaseInfo> {
  return requestJson<DatabaseInfo>(`/api/databases/${databaseId}/clone`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function activateDatabase(databaseId: string): Promise<DatabaseInfo> {
  return requestJson<DatabaseInfo>(`/api/databases/${databaseId}/activate`, {
    method: "POST",
  });
}

export function renameDatabase(
  databaseId: string,
  name: string
): Promise<DatabaseInfo> {
  return requestJson<DatabaseInfo>(`/api/databases/${databaseId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export function deleteDatabase(
  databaseId: string,
  token: string
): Promise<DatabaseInfo> {
  return requestJson<DatabaseInfo>(`/api/databases/${databaseId}`, {
    method: "DELETE",
    headers: {
      "X-Update-Token": token,
    },
  });
}

export async function fetchInventory(): Promise<Account[]> {
  const payload = await requestJson<InventoryPayload>("/api/inventory");
  return payload.records;
}

export async function previewInbound(
  text: string
): Promise<InboundPreviewRow[]> {
  const payload = await requestJson<{ rows: InboundPreviewRow[] }>(
    "/api/inbound/preview",
    {
      method: "POST",
      body: JSON.stringify({ text }),
    }
  );
  return payload.rows;
}

export function commitInbound(
  rows: Pick<InboundPreviewRow, "clientId" | "line">[],
  approvedPendingClientIds: string[]
): Promise<InboundCommitPayload> {
  return requestJson<InboundCommitPayload>("/api/inbound/commit", {
    method: "POST",
    body: JSON.stringify({ rows, approvedPendingClientIds }),
  });
}

export function previewFifo(quantity: number): Promise<FifoPreviewPayload> {
  return requestJson<FifoPreviewPayload>("/api/outbound/fifo/preview", {
    method: "POST",
    body: JSON.stringify({ quantity }),
  });
}

export function commitFifo(quantity: number): Promise<FifoCommitPayload> {
  return requestJson<FifoCommitPayload>("/api/outbound/fifo/commit", {
    method: "POST",
    body: JSON.stringify({ quantity }),
  });
}

export async function searchAccounts(query: string): Promise<SearchResult[]> {
  const payload = await requestJson<SearchPayload>(
    `/api/search?q=${encodeURIComponent(query)}`
  );
  return payload.results;
}

export async function fetchOutboundHistory(): Promise<OutboundRecord[]> {
  const payload = await requestJson<OutboundHistoryPayload>(
    "/api/outbound/history"
  );
  return payload.records;
}

export function outboundByUsername(
  username: string
): Promise<OutboundByUsernamePayload> {
  return requestJson<OutboundByUsernamePayload>("/api/outbound/by-username", {
    method: "POST",
    body: JSON.stringify({ username }),
  });
}

export function commitOutboundPaste(
  rows: Pick<OutboundPasteRow, "clientId" | "line">[]
): Promise<OutboundPasteCommitPayload> {
  return requestJson<OutboundPasteCommitPayload>("/api/outbound-paste/commit", {
    method: "POST",
    body: JSON.stringify({ rows }),
  });
}

export function ignoreClipboardText(text: string): Promise<{ ok: boolean }> {
  return requestJson<{ ok: boolean }>("/api/clipboard/ignore", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export function fetchUpdateStatus(): Promise<UpdateStatusPayload> {
  return requestJson<UpdateStatusPayload>("/api/runtime/update-status");
}

export function checkForUpdate(): Promise<UpdateStatusPayload> {
  return requestJson<UpdateStatusPayload>("/api/runtime/check-update", {
    method: "POST",
  });
}

export function triggerUpdate(token: string): Promise<UpdateStatusPayload> {
  return requestJson<UpdateStatusPayload>("/api/runtime/trigger-update", {
    method: "POST",
    headers: {
      "X-Update-Token": token,
    },
  });
}

export async function writeAppClipboardText(text: string): Promise<void> {
  await navigator.clipboard.writeText(text);
  try {
    await ignoreClipboardText(text);
  } catch {
    // Clipboard copy already succeeded; ignoring the watcher is best-effort.
  }
}

export async function writeOutboundClipboardText(text: string): Promise<void> {
  rememberOutboundClipboardText(text);
  try {
    await writeAppClipboardText(text);
  } catch (error) {
    clearOutboundClipboardText();
    throw error;
  }
}
