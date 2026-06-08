import type {
  Account,
  DatabaseInfo,
  DatabaseListPayload,
  DashboardPayload,
  FifoCommitPayload,
  FifoNoteEntry,
  FifoPreviewPayload,
  HistoryExportPayload,
  HistoryPayload,
  HistoryRecord,
  InboundCommitPayload,
  InboundHistoryPayload,
  InboundPreviewRow,
  InboundRecord,
  InventoryPayload,
  KlineBucket,
  KlinePayload,
  PaginatedMeta,
  OutboundByUsernamePayload,
  OutboundFromInboundHistoryPayload,
  OutboundHistoryPayload,
  OutboundRecord,
  OutboundPasteCommitPayload,
  OutboundPasteRow,
  ReinboundFromHistoryPayload,
  SearchPayload,
  SeparatorRule,
  SeparatorRuleListPayload,
  UpdateStatusPayload,
} from "@/types/account";
import {
  clearOutboundClipboardText,
  rememberOutboundClipboardText,
} from "@/lib/outbound-clipboard-guard";
import { readHttpErrorDetail } from "@/lib/http-error";
import { ClipboardCopyError, copyToClipboard } from "@/lib/clipboard";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export const DEFAULT_PAGE_SIZE = 50;

export type PaginatedResult<T> = PaginatedMeta & { records: T[] };

type QueryParamValue = string | number | string[] | undefined;

export function buildPaginationQuery(
  params: {
    page?: number;
    pageSize?: number;
    [key: string]: QueryParamValue;
  } = {}
): string {
  const search = new URLSearchParams();
  if (params.page != null) {
    search.set("page", String(params.page));
  }
  if (params.pageSize != null) {
    search.set("pageSize", String(params.pageSize));
  }
  for (const [key, value] of Object.entries(params)) {
    if (key === "page" || key === "pageSize" || value == null) {
      continue;
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        const trimmed = String(item).trim();
        if (trimmed) {
          search.append(key, trimmed);
        }
      }
      continue;
    }
    const text = String(value).trim();
    if (text) {
      search.set(key, text);
    }
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

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
    const detail =
      response.status === 401
        ? "需要远程访问令牌，请先完成远程访问验证"
        : await readHttpErrorDetail(
            response,
            response.status === 428 ? "请先配置数据库服务地址" : undefined
          );
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

export function fetchHistoryKline(
  options: {
    from?: string;
    to?: string;
    bucket?: KlineBucket | "auto";
    q?: string;
    ranges?: string[];
  } = {},
  init?: Pick<RequestInit, "signal">
): Promise<KlinePayload> {
  const query = buildPaginationQuery({
    from: options.from,
    to: options.to,
    bucket: options.bucket,
    q: options.q,
    ranges: options.ranges,
  });
  return requestJson<KlinePayload>(`/api/history/kline${query}`, init);
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

export async function fetchSeparatorRules(): Promise<SeparatorRule[]> {
  const payload = await requestJson<SeparatorRuleListPayload>(
    "/api/separator-rules"
  );
  return payload.rules;
}

export function createSeparatorRule(
  name: string,
  separator: string
): Promise<SeparatorRule> {
  return requestJson<SeparatorRule>("/api/separator-rules", {
    method: "POST",
    body: JSON.stringify({ name, separator }),
  });
}

export function updateSeparatorRule(
  ruleId: string,
  patch: { name?: string; separator?: string; enabled?: boolean }
): Promise<SeparatorRule> {
  return requestJson<SeparatorRule>(`/api/separator-rules/${ruleId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function deleteSeparatorRule(ruleId: string): Promise<{ ok: boolean }> {
  return requestJson<{ ok: boolean }>(`/api/separator-rules/${ruleId}`, {
    method: "DELETE",
  });
}

export async function fetchInventory(
  params: {
    page?: number;
    pageSize?: number;
    q?: string;
    sortBy?: "inboundAt" | "username";
    sortDir?: "asc" | "desc";
  } = {}
): Promise<PaginatedResult<Account>> {
  const query = buildPaginationQuery({
    page: params.page ?? 1,
    pageSize: params.pageSize ?? DEFAULT_PAGE_SIZE,
    q: params.q,
    sortBy: params.sortBy,
    sortDir: params.sortDir,
  });
  return requestJson<InventoryPayload>(`/api/inventory${query}`);
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

export type InboundCommitRow = Pick<
  InboundPreviewRow,
  "clientId" | "line" | "note" | "overwriteNote"
>;

export function commitInbound(
  rows: InboundCommitRow[],
  approvedPendingClientIds: string[]
): Promise<InboundCommitPayload> {
  return requestJson<InboundCommitPayload>("/api/inbound/commit", {
    method: "POST",
    body: JSON.stringify({ rows, approvedPendingClientIds }),
  });
}

function resolveOutboundHistoryRecordId(
  record: OutboundRecord | HistoryRecord
): string {
  if ("type" in record && record.type === "outbound") {
    const prefix = "outbound-";
    if (record.id.startsWith(prefix)) {
      return record.id.slice(prefix.length);
    }
  }
  return record.id;
}

export async function commitReInboundFromHistory(
  record: OutboundRecord | HistoryRecord
): Promise<ReinboundFromHistoryPayload> {
  const recordId = resolveOutboundHistoryRecordId(record);
  return requestJson<ReinboundFromHistoryPayload>(
    `/api/outbound/history/${encodeURIComponent(recordId)}/reinbound`,
    {
      method: "POST",
    }
  );
}

function resolveInboundHistoryRecordId(
  record: InboundRecord | HistoryRecord
): string {
  if ("type" in record && record.type === "inbound") {
    const prefix = "inbound-";
    if (record.id.startsWith(prefix)) {
      return record.id.slice(prefix.length);
    }
  }
  return record.id;
}

export function commitOutboundFromInboundHistory(
  record: InboundRecord | HistoryRecord
): Promise<OutboundFromInboundHistoryPayload> {
  const recordId = resolveInboundHistoryRecordId(record);
  return requestJson<OutboundFromInboundHistoryPayload>(
    `/api/inbound/history/${encodeURIComponent(recordId)}/outbound`,
    {
      method: "POST",
    }
  );
}

export function previewFifo(quantity: number): Promise<FifoPreviewPayload> {
  return requestJson<FifoPreviewPayload>("/api/outbound/fifo/preview", {
    method: "POST",
    body: JSON.stringify({ quantity }),
  });
}

export function commitFifo(
  quantity: number,
  notes: FifoNoteEntry[] = []
): Promise<FifoCommitPayload> {
  return requestJson<FifoCommitPayload>("/api/outbound/fifo/commit", {
    method: "POST",
    body: JSON.stringify({ quantity, notes }),
  });
}

export function searchAccounts(
  query: string,
  options: {
    page?: number;
    pageSize?: number;
    source?: "all" | "inventory" | "history";
  } = {}
): Promise<SearchPayload> {
  const path = buildPaginationQuery({
    q: query,
    page: options.page ?? 1,
    pageSize: options.pageSize ?? DEFAULT_PAGE_SIZE,
    source: options.source ?? "all",
  });
  return requestJson<SearchPayload>(`/api/search${path}`);
}

export async function fetchOutboundHistory(
  options: {
    page?: number;
    pageSize?: number;
    q?: string;
    ranges?: string[];
  } = {}
): Promise<PaginatedResult<OutboundRecord> & { inventoryUsernames?: string[] }> {
  return requestJson<OutboundHistoryPayload>(
    `/api/outbound/history${buildPaginationQuery({
      page: options.page ?? 1,
      pageSize: options.pageSize ?? DEFAULT_PAGE_SIZE,
      q: options.q,
      ranges: options.ranges,
    })}`
  );
}

export async function fetchInboundHistory(
  options: {
    page?: number;
    pageSize?: number;
    q?: string;
    ranges?: string[];
  } = {}
): Promise<PaginatedResult<InboundRecord>> {
  return requestJson<InboundHistoryPayload>(
    `/api/inbound/history${buildPaginationQuery({
      page: options.page ?? 1,
      pageSize: options.pageSize ?? DEFAULT_PAGE_SIZE,
      q: options.q,
      ranges: options.ranges,
    })}`
  );
}

export async function fetchUnifiedHistory(
  options: {
    page?: number;
    pageSize?: number;
    type?: "all" | "inbound" | "outbound";
    q?: string;
    ranges?: string[];
  } = {}
): Promise<PaginatedResult<HistoryRecord> & { inventoryUsernames?: string[] }> {
  const query = buildPaginationQuery({
    page: options.page ?? 1,
    pageSize: options.pageSize ?? DEFAULT_PAGE_SIZE,
    type: options.type && options.type !== "all" ? options.type : undefined,
    q: options.q,
    ranges: options.ranges,
  });
  return requestJson<HistoryPayload>(`/api/history${query}`);
}

export function exportHistoryText(options: {
  type?: "all" | "inbound" | "outbound";
  q?: string;
  ranges?: string[];
} = {}): Promise<HistoryExportPayload> {
  const query = buildPaginationQuery({
    type: options.type && options.type !== "all" ? options.type : undefined,
    q: options.q,
    ranges: options.ranges,
  });
  return requestJson<HistoryExportPayload>(`/api/history/export${query}`);
}

export function outboundByUsername(
  username: string,
  options?: { note?: string | null; overwriteNote?: boolean }
): Promise<OutboundByUsernamePayload> {
  return requestJson<OutboundByUsernamePayload>("/api/outbound/by-username", {
    method: "POST",
    body: JSON.stringify({ username, ...options }),
  });
}

export type OutboundPasteCommitRow = Pick<
  OutboundPasteRow,
  "clientId" | "line" | "note" | "overwriteNote"
>;

export function commitOutboundPaste(
  rows: OutboundPasteCommitRow[]
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
  const result = await copyToClipboard(text);
  if (!result.ok) {
    throw new ClipboardCopyError(result.text, result.reason);
  }
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
