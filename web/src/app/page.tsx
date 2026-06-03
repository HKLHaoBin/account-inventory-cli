"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  Check,
  Clipboard,
  Download,
  Minus,
  Package,
  Plus,
  Trash2,
  Upload,
} from "lucide-react";
import { StatCard } from "@/components/ui/stat-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/input";
import { BatchNoteControls } from "@/components/notes/batch-note-controls";
import { OutboundNoteField } from "@/components/notes/outbound-note-field";
import { OutboundCopyButton } from "@/components/outbound/outbound-copy-button";
import { useLastOutboundClipboard } from "@/hooks/use-last-outbound-clipboard";
import {
  commitFifo,
  commitInbound,
  fetchDashboard,
  previewFifo,
} from "@/lib/api";
import { subscribeDatabaseChanged } from "@/lib/database-events";
import { downloadTextFile } from "@/lib/download";
import { shouldIgnoreInboundClipboardText } from "@/lib/outbound-clipboard-guard";
import { isClipboardMessage, getClipboardWsUrl } from "@/lib/ws";
import { parseAccountLine, parseLines } from "@/lib/parser";
import { useSeparatorRules } from "@/lib/use-separator-rules";
import { cn, formatDateTime, formatRelativeTime, maskValue } from "@/lib/utils";
import type {
  Account,
  ActivityItem,
  DashboardPayload,
  FifoPreviewPayload,
  InboundCategory,
  InboundCommitResultRow,
  InboundPreviewRow,
  FifoNoteEntry,
} from "@/types/account";

const EMPTY_DASHBOARD: DashboardPayload = {
  stats: {
    inventoryCount: 0,
    todayInbound: 0,
    todayOutbound: 0,
    pendingCount: 0,
  },
  database: {
    id: "",
    name: "默认数据库",
    fileName: "accounts.db",
    path: "data/accounts.db",
    createdAt: "",
    active: true,
    inventoryCount: 0,
    todayInbound: 0,
    todayOutbound: 0,
  },
  fifoPreview: [],
  recentActivities: [],
};

const CATEGORY_LABELS: Record<InboundCategory, string> = {
  ready: "待检测",
  duplicate: "库存重复",
  pending: "曾出库待确认",
  invalid: "格式错误",
  batchDuplicate: "批次内重复",
};

type InboundCountKey = InboundCategory | "success";

const COUNT_LABELS: Record<InboundCountKey, string> = {
  success: "入库成功",
  ...CATEGORY_LABELS,
};

function categoryBadge(category: InboundCategory | "success") {
  if (category === "success") return "success";
  if (category === "ready") return "success";
  if (category === "pending") return "warning";
  if (category === "duplicate" || category === "batchDuplicate") return "error";
  return "secondary";
}

function isCommitResult(
  row: InboundPreviewRow | InboundCommitResultRow
): row is InboundCommitResultRow {
  return "status" in row;
}

function rowTone(row: InboundPreviewRow | InboundCommitResultRow) {
  if (isCommitResult(row)) {
    if (row.status === "success") return "bg-emerald-50/80 dark:bg-emerald-950/25";
    if (row.status === "warning") return "bg-amber-50/80 dark:bg-amber-950/25";
    if (row.status === "error") return "bg-red-50/80 dark:bg-red-950/25";
  }
  if (row.category === "ready") return "bg-emerald-50/40 dark:bg-emerald-950/10";
  if (row.category === "pending") return "bg-amber-50/50 dark:bg-amber-950/15";
  if (row.category === "invalid") return "bg-muted/40";
  if (row.category === "duplicate" || row.category === "batchDuplicate") {
    return "bg-red-50/60 dark:bg-red-950/20";
  }
  return "";
}

function displayCategory(row: InboundPreviewRow | InboundCommitResultRow) {
  return isCommitResult(row) && row.status === "success" ? "success" : row.category;
}

function canCommitRow(
  row: InboundPreviewRow | InboundCommitResultRow,
  approvedPendingIds: Set<string>
) {
  if (!isCommitResult(row)) return true;
  return row.status === "warning" && approvedPendingIds.has(row.clientId);
}

function AccountCell({ value }: { value?: string | null }) {
  if (!value) return <span className="text-muted-foreground">-</span>;
  return <span className="font-mono text-xs">{value}</span>;
}

function buildDraftRows(text: string, separators: string[]): InboundPreviewRow[] {
  return parseLines(text).map((line, index) => {
    const clientId = `line-${index + 1}`;
    try {
      const account = parseAccountLine(line, separators);
      return {
        clientId,
        line,
        username: account.username,
        password: account.password,
        email: account.email,
        emailPassword: account.emailPassword,
        url: account.url,
        category: "ready",
        reason: "点击确认入库后检测库存状态",
      };
    } catch (error) {
      return {
        clientId,
        line,
        category: "invalid",
        reason: error instanceof Error ? error.message : "格式错误",
      };
    }
  });
}

function FifoTable({
  rows,
  mobileLimit,
  fifoNotesByUsername,
  onFifoNoteChange,
}: {
  rows: Account[];
  mobileLimit?: number;
  fifoNotesByUsername?: Record<
    string,
    { note: string; overwriteNote: boolean }
  >;
  onFifoNoteChange?: (
    username: string,
    patch: Partial<{ note: string; overwriteNote: boolean }>
  ) => void;
}) {
  const showNotes = Boolean(onFifoNoteChange);
  if (rows.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground">
        当前无可预览库存
      </p>
    );
  }

  const mobileRows = mobileLimit ? rows.slice(0, mobileLimit) : rows;
  const remaining = rows.length - mobileRows.length;

  return (
    <>
      <div className="space-y-2 md:hidden">
        {mobileRows.map((account, index) => (
          <div
            key={`${account.id}-${index}-mobile`}
            className="rounded-xl border border-border bg-muted/20 px-3 py-2.5"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-xs font-semibold text-primary">
                  {index + 1}
                </span>
                <span className="truncate font-mono text-sm">{account.username}</span>
              </div>
              {index === 0 && (
                <Badge variant="fifo" className="shrink-0 text-[9px]">
                  队首
                </Badge>
              )}
            </div>
            <div className="mt-2 space-y-1 text-xs text-muted-foreground">
              <p className="font-mono">密码 {maskValue(account.password)}</p>
              <p className="whitespace-nowrap">
                入库 {formatDateTime(account.inboundAt)}
              </p>
            </div>
            {showNotes && (
              <OutboundNoteField
                existingNote={account.note}
                value={
                  fifoNotesByUsername?.[account.username]?.note ??
                  account.note ??
                  ""
                }
                onChange={(note) =>
                  onFifoNoteChange?.(account.username, {
                    note,
                    overwriteNote: false,
                  })
                }
                overwriteNote={
                  fifoNotesByUsername?.[account.username]?.overwriteNote ??
                  false
                }
                onOverwriteNoteChange={(overwriteNote) =>
                  onFifoNoteChange?.(account.username, { overwriteNote })
                }
                className="mt-2 w-full"
                inputClassName="h-8 w-full text-xs"
              />
            )}
          </div>
        ))}
        {remaining > 0 && (
          <p className="rounded-xl border border-dashed border-border px-3 py-2 text-center text-xs text-muted-foreground">
            还有 {remaining} 条
          </p>
        )}
      </div>

      <div className="hidden overflow-x-auto rounded-xl border border-border md:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/40">
              <th className="px-3 py-2.5 text-left font-medium">#</th>
              <th className="px-3 py-2.5 text-left font-medium">账号</th>
              <th className="px-3 py-2.5 text-left font-medium">密码</th>
              <th className="px-3 py-2.5 text-left font-medium">入库时间</th>
              {showNotes && (
                <th className="px-3 py-2.5 text-left font-medium">备注</th>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((account, index) => (
              <tr key={`${account.id}-${index}`} className="border-b border-border last:border-0">
                <td className="px-3 py-2.5 text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    {index + 1}
                    {index === 0 && (
                      <Badge variant="fifo" className="text-[9px]">
                        队首
                      </Badge>
                    )}
                  </span>
                </td>
                <td className="px-3 py-2.5 font-mono">{account.username}</td>
                <td className="px-3 py-2.5 font-mono text-xs">
                  {maskValue(account.password)}
                </td>
                <td className="px-3 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                  {formatDateTime(account.inboundAt)}
                </td>
                {showNotes && (
                  <td className="min-w-[140px] px-3 py-2.5">
                    <OutboundNoteField
                      existingNote={account.note}
                      value={
                        fifoNotesByUsername?.[account.username]?.note ??
                        account.note ??
                        ""
                      }
                      onChange={(note) =>
                        onFifoNoteChange?.(account.username, {
                          note,
                          overwriteNote: false,
                        })
                      }
                      overwriteNote={
                        fifoNotesByUsername?.[account.username]?.overwriteNote ??
                        false
                      }
                      onOverwriteNoteChange={(overwriteNote) =>
                        onFifoNoteChange?.(account.username, { overwriteNote })
                      }
                      inputClassName="h-8 text-xs"
                    />
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function ActivitiesList({ activities }: { activities: ActivityItem[] }) {
  if (activities.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground">
        暂无最近活动
      </p>
    );
  }

  const renderItem = (activity: ActivityItem) => (
    <div
      key={activity.id}
      className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
    >
      <div className="flex min-w-0 items-center gap-3">
        <Badge variant={activity.type === "inbound" ? "success" : "info"}>
          {activity.type === "inbound" ? "入库" : "出库"}
        </Badge>
        <span className="truncate font-mono text-sm">{activity.username}</span>
      </div>
      <span className="shrink-0 text-xs text-muted-foreground">
        {formatRelativeTime(activity.timestamp)}
      </span>
    </div>
  );

  return (
    <>
      <div className="divide-y divide-border md:hidden">
        {activities.slice(0, 5).map(renderItem)}
      </div>
      <div className="hidden divide-y divide-border md:block">
        {activities.slice(0, 10).map(renderItem)}
      </div>
    </>
  );
}

export default function DashboardPage() {
  const wsTimerRef = useRef<number | null>(null);
  const inboundTextRef = useRef("");
  const resultRowsRef = useRef<Map<string, InboundCommitResultRow>>(new Map());
  const inboundTextareaRef = useRef<HTMLTextAreaElement>(null);
  const fifoQuantityRef = useRef<HTMLInputElement>(null);
  const { enabledSeparators, loading: rulesLoading, error: rulesError } =
    useSeparatorRules();
  const rulesReady = !rulesLoading && !rulesError;
  const [dashboard, setDashboard] = useState<DashboardPayload>(EMPTY_DASHBOARD);
  const [dashboardError, setDashboardError] = useState("");
  const [text, setText] = useState("");
  const [previewRows, setPreviewRows] = useState<InboundPreviewRow[]>([]);
  const [deletedIds, setDeletedIds] = useState<Set<string>>(new Set());
  const [pendingCursorId, setPendingCursorId] = useState<string | null>(null);
  const [approvedPendingIds, setApprovedPendingIds] = useState<Set<string>>(
    new Set()
  );
  const [resultRows, setResultRows] = useState<Map<string, InboundCommitResultRow>>(
    new Map()
  );
  const [previewError, setPreviewError] = useState("");
  const [inboundBusy, setInboundBusy] = useState(false);
  const [clipboardState, setClipboardState] = useState("连接剪贴板检测中");
  const [keyboardMessage, setKeyboardMessage] = useState("");
  const [fifoQuantity, setFifoQuantity] = useState(1);
  const [fifoPreview, setFifoPreview] = useState<FifoPreviewPayload>({
    max: 0,
    quantity: 0,
    rows: [],
  });
  const [fifoBusy, setFifoBusy] = useState(false);
  const [fifoMessage, setFifoMessage] = useState("");
  const [fifoNotes, setFifoNotes] = useState<FifoNoteEntry[]>([]);
  const {
    clipboardText: fifoClipboardText,
    remember: rememberFifoClipboard,
    clear: clearFifoClipboard,
    copy: copyFifoClipboard,
    copying: fifoCopying,
    copied: fifoCopied,
  } = useLastOutboundClipboard();

  const replaceInboundText = useCallback((value: string) => {
    inboundTextRef.current = value;
    resultRowsRef.current = new Map();
    setText(value);
    setPreviewRows(rulesReady ? buildDraftRows(value, enabledSeparators) : []);
    setDeletedIds(new Set());
    setPendingCursorId(null);
    setApprovedPendingIds(new Set());
    setResultRows(new Map());
    setPreviewError("");
    setKeyboardMessage("");
  }, [enabledSeparators, rulesReady]);

  const appendInboundText = useCallback((value: string) => {
    const nextValue = value.trim();
    if (!nextValue) return;
    const currentValue = inboundTextRef.current.trimEnd();
    const mergedValue = currentValue ? `${currentValue}\n${nextValue}` : nextValue;
    inboundTextRef.current = mergedValue;
    resultRowsRef.current = new Map();
    setText(mergedValue);
    setPreviewRows(rulesReady ? buildDraftRows(mergedValue, enabledSeparators) : []);
    setResultRows(new Map());
    setPreviewError("");
  }, [enabledSeparators, rulesReady]);

  const loadDashboard = useCallback(async () => {
    try {
      const payload = await fetchDashboard();
      setDashboard(payload);
      setDashboardError("");
      return payload;
    } catch (error) {
      setDashboardError(error instanceof Error ? error.message : "加载仪表盘失败");
      return null;
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadDashboard();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadDashboard]);

  useEffect(
    () => subscribeDatabaseChanged(() => void loadDashboard()),
    [loadDashboard]
  );

  useEffect(() => {
    if (!inboundTextRef.current || !rulesReady) return;
    setPreviewRows(buildDraftRows(inboundTextRef.current, enabledSeparators));
  }, [enabledSeparators, rulesReady]);

  function updatePreviewRow(clientId: string, patch: Partial<InboundPreviewRow>) {
    setPreviewRows((rows) =>
      rows.map((row) => (row.clientId === clientId ? { ...row, ...patch } : row))
    );
  }

  const fifoNotesByUsername = useMemo(
    () =>
      Object.fromEntries(
        fifoNotes.map((entry) => [
          entry.username,
          {
            note: entry.note ?? "",
            overwriteNote: entry.overwriteNote ?? false,
          },
        ])
      ),
    [fifoNotes]
  );

  function updateFifoNote(
    username: string,
    patch: Partial<{ note: string; overwriteNote: boolean }>
  ) {
    setFifoNotes((entries) =>
      entries.map((entry) =>
        entry.username === username
          ? {
              ...entry,
              ...(patch.note !== undefined
                ? { note: patch.note, overwriteNote: false }
                : {}),
              ...(patch.overwriteNote !== undefined
                ? { overwriteNote: patch.overwriteNote }
                : {}),
            }
          : entry
      )
    );
  }

  useEffect(() => {
    let socket: WebSocket | null = null;
    let stopped = false;

    const connect = () => {
      socket = new WebSocket(getClipboardWsUrl());
      socket.onopen = () => setClipboardState("剪贴板检测已连接");
      socket.onmessage = (event) => {
        try {
          const value = JSON.parse(event.data) as unknown;
          if (!isClipboardMessage(value)) return;
          if (shouldIgnoreInboundClipboardText(value.text)) {
            setClipboardState("已忽略本次出库复制内容");
            return;
          }
          if (resultRowsRef.current.size > 0) {
            replaceInboundText(value.text);
          } else {
            appendInboundText(value.text);
          }
          setClipboardState(
            `已从剪贴板载入 ${value.validLines.length} 条，剔除 ${value.rejectedCount} 条`
          );
        } catch {
          setClipboardState("剪贴板消息解析失败");
        }
      };
      socket.onclose = () => {
        if (stopped) return;
        setClipboardState("剪贴板检测重连中");
        wsTimerRef.current = window.setTimeout(connect, 2000);
      };
      socket.onerror = () => {
        setClipboardState("剪贴板检测连接失败");
        socket?.close();
      };
    };

    connect();
    return () => {
      stopped = true;
      if (wsTimerRef.current !== null) window.clearTimeout(wsTimerRef.current);
      socket?.close();
    };
  }, [appendInboundText, replaceInboundText]);

  useEffect(() => {
    let ignore = false;
    async function loadPreview() {
      try {
        const payload = await previewFifo(fifoQuantity);
        if (ignore) return;
        setFifoPreview(payload);
        setFifoNotes((current) => {
          const byUsername = new Map(
            current.map((entry) => [entry.username, entry])
          );
          return payload.rows.map((row) => {
            const existing = byUsername.get(row.username);
            return {
              username: row.username,
              note: existing?.note ?? row.note ?? "",
              overwriteNote: existing?.overwriteNote ?? false,
            };
          });
        });
        setFifoMessage("");
      } catch (error) {
        if (ignore) return;
        setFifoMessage(error instanceof Error ? error.message : "FIFO 预览失败");
      }
    }
    loadPreview();
    return () => {
      ignore = true;
    };
  }, [fifoQuantity, dashboard.stats.inventoryCount]);

  useEffect(() => {
    clearFifoClipboard();
  }, [fifoQuantity, clearFifoClipboard]);

  const displayedRows = useMemo(() => {
    return previewRows
      .filter((row) => !deletedIds.has(row.clientId))
      .map((row) => resultRows.get(row.clientId) ?? row);
  }, [deletedIds, previewRows, resultRows]);

  const pendingRows = useMemo(
    () => displayedRows.filter((row) => displayCategory(row) === "pending"),
    [displayedRows]
  );

  const counts = useMemo(() => {
    return displayedRows.reduce(
      (acc, row) => {
        acc[displayCategory(row)] += 1;
        return acc;
      },
      {
        success: 0,
        ready: 0,
        duplicate: 0,
        pending: 0,
        invalid: 0,
        batchDuplicate: 0,
      } as Record<InboundCountKey, number>
    );
  }, [displayedRows]);

  const commitRows = displayedRows
    .filter((row) => canCommitRow(row, approvedPendingIds))
    .map((row) => ({
      clientId: row.clientId,
      line: row.line,
      note: row.note,
      overwriteNote: row.overwriteNote,
    }));
  const approvedReadyCount = commitRows.length;
  const fifoChips = useMemo(() => {
    const max = fifoPreview.max || dashboard.stats.inventoryCount || 0;
    return Array.from(new Set([1, 5, 10, max].filter((n) => n > 0)));
  }, [dashboard.stats.inventoryCount, fifoPreview.max]);
  const dashboardStats = [
    {
      title: "当前库存",
      value: dashboard.stats.inventoryCount,
      subtitle: "条账号",
      icon: Package,
      variant: "default" as const,
    },
    {
      title: "今日入库",
      value: dashboard.stats.todayInbound,
      subtitle: "条",
      icon: ArrowDownToLine,
      variant: "success" as const,
    },
    {
      title: "今日出库",
      value: dashboard.stats.todayOutbound,
      subtitle: "条",
      icon: ArrowUpFromLine,
      variant: "info" as const,
    },
    {
      title: "待处理",
      value: counts.pending,
      subtitle: "待确认",
      icon: Clipboard,
      variant: "warning" as const,
    },
  ];

  function handleTextChange(value: string) {
    inboundTextRef.current = value;
    resultRowsRef.current = new Map();
    setText(value);
    setPreviewRows(rulesReady ? buildDraftRows(value, enabledSeparators) : []);
    setDeletedIds(new Set());
    setPendingCursorId(null);
    setApprovedPendingIds(new Set());
    setResultRows(new Map());
    setKeyboardMessage("");
  }

  function cancelPendingRows(ids: string[]) {
    if (ids.length === 0) return;
    setDeletedIds((prev) => {
      const next = new Set(prev);
      for (const id of ids) next.add(id);
      return next;
    });
    setApprovedPendingIds((prev) => {
      const next = new Set(prev);
      for (const id of ids) next.delete(id);
      return next;
    });
    setPendingCursorId((current) => (current && ids.includes(current) ? null : current));
    setKeyboardMessage(`已取消 ${ids.length} 条待确认项`);
  }

  async function handleInboundCommit() {
    if (commitRows.length === 0) return;
    setInboundBusy(true);
    try {
      const payload = await commitInbound(
        commitRows,
        Array.from(approvedPendingIds)
      );
      const nextResultRows = new Map(resultRowsRef.current);
      for (const row of payload.rows) nextResultRows.set(row.clientId, row);
      resultRowsRef.current = nextResultRows;
      setResultRows(nextResultRows);
      await loadDashboard();
      setFifoQuantity((current) => Math.max(1, current));
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "入库提交失败");
    } finally {
      setInboundBusy(false);
    }
  }

  async function handleFifoCommit() {
    if (fifoPreview.quantity <= 0) return;
    setFifoBusy(true);
    setFifoMessage("");
    try {
      const payload = await commitFifo(fifoQuantity, fifoNotes);
      const text = payload.clipboardText ?? "";
      rememberFifoClipboard(text);
      const copiedOk = text ? await copyFifoClipboard(text) : true;
      setFifoMessage(
        copiedOk
          ? `已出库 ${payload.quantity} 条并复制到剪贴板`
          : `已出库 ${payload.quantity} 条，复制失败请点重新复制`
      );
      await loadDashboard();
    } catch (error) {
      setFifoMessage(error instanceof Error ? error.message : "FIFO 出库失败");
    } finally {
      setFifoBusy(false);
    }
  }

  async function handleFifoDownload() {
    if (fifoPreview.quantity <= 0) return;
    setFifoBusy(true);
    setFifoMessage("");
    try {
      const payload = await commitFifo(fifoQuantity, fifoNotes);
      rememberFifoClipboard(payload.clipboardText ?? "");
      if (payload.clipboardText) {
        downloadTextFile(payload.clipboardText);
      }
      setFifoMessage(`已出库 ${payload.quantity} 条并下载 TXT`);
      await loadDashboard();
    } catch (error) {
      setFifoMessage(error instanceof Error ? error.message : "FIFO 出库失败");
    } finally {
      setFifoBusy(false);
    }
  }

  async function handleFifoCopy() {
    setFifoMessage("");
    const ok = await copyFifoClipboard();
    if (!ok && fifoClipboardText) {
      setFifoMessage("复制到剪贴板失败，请重试");
    }
  }

  useEffect(() => {
    let nextCursorId: string | null = null;
    if (pendingRows.length === 0) {
      nextCursorId = null;
    } else if (
      pendingCursorId &&
      pendingRows.some((row) => row.clientId === pendingCursorId)
    ) {
      return;
    } else {
      nextCursorId = pendingRows[0].clientId;
    }

    const timer = window.setTimeout(() => {
      setPendingCursorId(nextCursorId);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [pendingCursorId, pendingRows]);

  useEffect(() => {
    const isEditableTarget = (target: EventTarget | null) => {
      if (!(target instanceof HTMLElement)) return false;
      const tag = target.tagName;
      return (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        target.isContentEditable
      );
    };

    const cyclePending = (direction: 1 | -1) => {
      if (pendingRows.length === 0) return;
      const currentIndex = Math.max(
        0,
        pendingRows.findIndex((row) => row.clientId === pendingCursorId)
      );
      const nextIndex =
        (currentIndex + direction + pendingRows.length) % pendingRows.length;
      setPendingCursorId(pendingRows[nextIndex].clientId);
    };

    const handler = (event: KeyboardEvent) => {
      if (isEditableTarget(event.target)) return;

      if (event.key === "i" || event.key === "I") {
        event.preventDefault();
        inboundTextareaRef.current?.focus();
        return;
      }

      if (event.key === "f" || event.key === "F") {
        event.preventDefault();
        fifoQuantityRef.current?.focus();
        fifoQuantityRef.current?.select();
        return;
      }

      if (pendingRows.length === 0) return;

      if (event.key === "ArrowUp") {
        event.preventDefault();
        cyclePending(-1);
        return;
      }

      if (event.key === "ArrowDown") {
        event.preventDefault();
        cyclePending(1);
        return;
      }

      const currentId = pendingCursorId ?? pendingRows[0].clientId;

      if (event.key === " " || event.key === "Enter") {
        event.preventDefault();
        setApprovedPendingIds((prev) => {
          const next = new Set(prev);
          if (next.has(currentId)) next.delete(currentId);
          else next.add(currentId);
          return next;
        });
        setKeyboardMessage("已切换当前待确认项");
        return;
      }

      if (event.key === "y" || event.key === "Y") {
        event.preventDefault();
        setApprovedPendingIds((prev) => new Set(prev).add(currentId));
        setKeyboardMessage("已批准当前待确认项");
        return;
      }

      if (event.key === "n" || event.key === "N") {
        event.preventDefault();
        const selectedIds = pendingRows
          .map((row) => row.clientId)
          .filter((id) => approvedPendingIds.has(id));
        cancelPendingRows(selectedIds.length > 0 ? selectedIds : [currentId]);
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        const unapprovedIds = pendingRows
          .map((row) => row.clientId)
          .filter((id) => !approvedPendingIds.has(id));
        cancelPendingRows(unapprovedIds);
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [approvedPendingIds, pendingCursorId, pendingRows]);

  return (
    <div className="space-y-4 lg:space-y-6">
      <div>
        <h1 className="text-xl font-bold tracking-tight sm:text-2xl">
          {dashboard.database.name} 仪表盘
        </h1>
        <p className="mt-1 hidden text-sm text-muted-foreground sm:block">
          一屏处理批量入库、快速 FIFO 出库与库存动态
        </p>
        {dashboardError && (
          <p className="mt-2 text-sm text-red-600">{dashboardError}</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 sm:hidden">
        {dashboardStats.map((stat) => {
          const Icon = stat.icon;
          return (
            <div
              key={stat.title}
              className="flex min-w-0 items-center justify-between gap-2 rounded-xl border border-border bg-card px-3 py-2.5"
            >
              <div className="min-w-0">
                <p className="truncate text-xs text-muted-foreground">{stat.title}</p>
                <p className="text-xl font-bold tracking-tight">{stat.value}</p>
              </div>
              <Icon className="h-4 w-4 shrink-0 text-primary" />
            </div>
          );
        })}
      </div>

      <div className="hidden gap-4 sm:grid sm:grid-cols-2 xl:grid-cols-4">
        {dashboardStats.map((stat) => (
          <StatCard
            key={stat.title}
            title={stat.title}
            value={stat.value}
            subtitle={stat.subtitle}
            icon={stat.icon}
            variant={stat.variant}
          />
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(340px,0.65fr)]">
        <Card>
          <CardHeader className="gap-3 p-4 pb-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4 sm:space-y-0 sm:p-6 sm:pb-4">
            <div className="min-w-0">
              <CardTitle className="flex items-center gap-2 text-base">
                <Download className="h-4 w-4 text-emerald-600" />
                批量入库
              </CardTitle>
              <p className="mt-1 truncate text-xs text-muted-foreground sm:whitespace-normal">
                {clipboardState}
              </p>
              {rulesLoading && (
                <p className="mt-1 text-xs text-muted-foreground">加载分隔规则中…</p>
              )}
              {rulesError && (
                <p className="mt-1 text-xs text-red-600">{rulesError}</p>
              )}
              <p className="mt-1 hidden text-xs text-muted-foreground md:block">
                I 聚焦输入 · ↑↓ 移动待确认 · Space/Enter 切换 · Y 批准 · N 取消 · Esc 取消未批准
              </p>
            </div>
            <div className="flex flex-wrap gap-2 sm:justify-end">
              <Button
                variant="secondary"
                size="sm"
                onClick={() =>
                  setApprovedPendingIds(
                    new Set(
                      displayedRows
                        .filter((row) => displayCategory(row) === "pending")
                        .map((row) => row.clientId)
                    )
                  )
                }
                disabled={counts.pending === 0}
              >
                批准全部待确认
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleTextChange("")}
                disabled={!text}
              >
                <Trash2 className="h-4 w-4" />
                清空
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4 p-4 pt-0 sm:p-6 sm:pt-0">
            <Textarea
              ref={inboundTextareaRef}
              value={text}
              onChange={(event) => handleTextChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.ctrlKey && event.key === "Enter") {
                  event.preventDefault();
                  void handleInboundCommit();
                }
              }}
              placeholder="使用已启用分隔规则，示例：账号----密码----邮箱----邮箱密码----网址"
              className="min-h-[150px] font-mono text-xs"
            />

            <div className="flex flex-wrap gap-2">
              {(Object.keys(COUNT_LABELS) as InboundCountKey[]).map((category) => (
                <Badge key={category} variant={categoryBadge(category)}>
                  {COUNT_LABELS[category]} {counts[category]}
                </Badge>
              ))}
            </div>

            {previewError && <p className="text-sm text-red-600">{previewError}</p>}
            {keyboardMessage && (
              <p className="text-xs text-primary">{keyboardMessage}</p>
            )}

            <BatchNoteControls
              rows={previewRows}
              onRowsChange={setPreviewRows}
              disabled={inboundBusy || rulesLoading || !!rulesError}
            />

            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-3">
              <Button
                className="w-full sm:w-auto"
                onClick={handleInboundCommit}
                disabled={
                  inboundBusy || commitRows.length === 0 || rulesLoading || !!rulesError
                }
              >
                <Check className="h-4 w-4" />
                确认入库 ({approvedReadyCount})
              </Button>
              <span className="text-xs text-muted-foreground">
                未批准的曾出库条目会在提交后标记为取消
              </span>
            </div>

            <div className="hidden overflow-x-auto rounded-xl border border-border lg:block">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/40">
                    <th className="w-10 px-3 py-2.5 text-left font-medium">确认</th>
                    <th className="px-3 py-2.5 text-left font-medium">状态</th>
                    <th className="px-3 py-2.5 text-left font-medium">账号</th>
                    <th className="px-3 py-2.5 text-left font-medium">密码</th>
                    <th className="px-3 py-2.5 text-left font-medium">邮箱</th>
                    <th className="px-3 py-2.5 text-left font-medium">网址</th>
                    <th className="px-3 py-2.5 text-left font-medium">备注</th>
                    <th className="px-3 py-2.5 text-left font-medium">信息</th>
                    <th className="w-12 px-3 py-2.5 text-left font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {displayedRows.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="px-3 py-8 text-center text-muted-foreground">
                        输入账号文本后会自动转换为表格
                      </td>
                    </tr>
                  ) : (
                    displayedRows.map((row) => {
                      const category = displayCategory(row);
                      const isPending = category === "pending";
                      const isKeyboardCursor = row.clientId === pendingCursorId;
                      const resultMessage = isCommitResult(row)
                        ? row.message
                        : row.reason ?? "";
                      return (
                        <tr
                          key={row.clientId}
                          className={cn(
                            "border-b border-border last:border-0",
                            rowTone(row),
                            isKeyboardCursor &&
                              "outline outline-2 outline-primary/40 outline-offset-[-2px]"
                          )}
                          onClick={() => {
                            if (isPending) setPendingCursorId(row.clientId);
                          }}
                        >
                          <td className="px-3 py-2.5">
                            {isPending ? (
                              <input
                                type="checkbox"
                                checked={approvedPendingIds.has(row.clientId)}
                                onChange={(event) => {
                                  setApprovedPendingIds((prev) => {
                                    const next = new Set(prev);
                                    if (event.target.checked) next.add(row.clientId);
                                    else next.delete(row.clientId);
                                    return next;
                                  });
                                }}
                                aria-label={`批准 ${row.username ?? row.line}`}
                              />
                            ) : (
                              <span className="text-muted-foreground">-</span>
                            )}
                          </td>
                          <td className="px-3 py-2.5">
                            <Badge variant={categoryBadge(category)}>
                              {COUNT_LABELS[category]}
                            </Badge>
                          </td>
                          <td className="px-3 py-2.5">
                            <AccountCell value={row.username} />
                          </td>
                          <td className="px-3 py-2.5">
                            <AccountCell value={row.password} />
                          </td>
                          <td className="px-3 py-2.5">
                            <AccountCell value={row.email} />
                          </td>
                          <td className="max-w-[180px] truncate px-3 py-2.5">
                            <AccountCell value={row.url} />
                          </td>
                          <td className="min-w-[140px] px-3 py-2.5">
                            <OutboundNoteField
                              value={row.note ?? ""}
                              onChange={(note) =>
                                updatePreviewRow(row.clientId, {
                                  note,
                                  overwriteNote: false,
                                })
                              }
                              overwriteNote={row.overwriteNote ?? false}
                              onOverwriteNoteChange={(overwriteNote) =>
                                updatePreviewRow(row.clientId, { overwriteNote })
                              }
                              disabled={
                                isCommitResult(row) && row.status === "success"
                              }
                              inputClassName="h-8 text-xs"
                            />
                          </td>
                          <td className="px-3 py-2.5 text-xs text-muted-foreground">
                            {resultMessage ||
                              (row.lastOutboundAt
                                ? `最近出库：${formatDateTime(row.lastOutboundAt)}`
                                : "-")}
                          </td>
                          <td className="px-3 py-2.5">
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() =>
                                setDeletedIds((prev) => new Set(prev).add(row.clientId))
                              }
                              aria-label="删除条目"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            <div className="space-y-2 lg:hidden">
              {displayedRows.length === 0 ? (
                <p className="rounded-xl border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
                  输入账号文本后会自动转换为表格
                </p>
              ) : (
                displayedRows.map((row) => {
                  const category = displayCategory(row);
                  const isPending = category === "pending";
                  const isKeyboardCursor = row.clientId === pendingCursorId;
                  const resultMessage = isCommitResult(row)
                    ? row.message
                    : row.reason ?? "";
                  return (
                    <div
                      key={`${row.clientId}-mobile`}
                      className={cn(
                        "rounded-xl border border-border p-3",
                        rowTone(row),
                        isKeyboardCursor && "ring-2 ring-primary/35"
                      )}
                      onClick={() => {
                        if (isPending) setPendingCursorId(row.clientId);
                      }}
                    >
                      <div className="flex items-start gap-3">
                        <div className="pt-0.5">
                          {isPending ? (
                            <input
                              type="checkbox"
                              className="h-5 w-5"
                              checked={approvedPendingIds.has(row.clientId)}
                              onChange={(event) => {
                                setApprovedPendingIds((prev) => {
                                  const next = new Set(prev);
                                  if (event.target.checked) next.add(row.clientId);
                                  else next.delete(row.clientId);
                                  return next;
                                });
                              }}
                              aria-label={`批准 ${row.username ?? row.line}`}
                            />
                          ) : (
                            <span className="block h-5 w-5 rounded-md border border-border bg-background" />
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <Badge variant={categoryBadge(category)}>
                              {COUNT_LABELS[category]}
                            </Badge>
                            <span className="truncate font-mono text-sm font-medium">
                              {row.username ?? row.line}
                            </span>
                          </div>
                          <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                            {row.password && (
                              <p className="truncate font-mono">
                                密码 {maskValue(row.password)}
                              </p>
                            )}
                            {(row.email || row.url) && (
                              <p className="truncate font-mono">
                                {row.email ?? row.url}
                              </p>
                            )}
                            <OutboundNoteField
                              value={row.note ?? ""}
                              onChange={(note) =>
                                updatePreviewRow(row.clientId, {
                                  note,
                                  overwriteNote: false,
                                })
                              }
                              overwriteNote={row.overwriteNote ?? false}
                              onOverwriteNoteChange={(overwriteNote) =>
                                updatePreviewRow(row.clientId, { overwriteNote })
                              }
                              disabled={
                                isCommitResult(row) && row.status === "success"
                              }
                              className="mt-2 w-full"
                              inputClassName="h-8 w-full text-xs"
                            />
                            <p className="break-words whitespace-pre-wrap">
                              {resultMessage ||
                                (row.lastOutboundAt
                                  ? `最近出库：${formatDateTime(row.lastOutboundAt)}`
                                  : "等待确认入库时检测")}
                            </p>
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="shrink-0"
                          onClick={(event) => {
                            event.stopPropagation();
                            setDeletedIds((prev) => new Set(prev).add(row.clientId));
                          }}
                          aria-label="删除条目"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="p-4 pb-3 sm:p-6 sm:pb-4">
            <CardTitle className="flex items-center gap-2 text-base">
              <Upload className="h-4 w-4 text-primary" />
              快速 FIFO 出库
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 p-4 pt-0 sm:p-6 sm:pt-0">
            <div className="flex items-center justify-center gap-3">
              <Button
                variant="outline"
                size="icon"
                onClick={() => setFifoQuantity((value) => Math.max(0, value - 1))}
                disabled={fifoQuantity <= 0}
              >
                <Minus className="h-4 w-4" />
              </Button>
              <input
                ref={fifoQuantityRef}
                type="number"
                value={fifoQuantity}
                onChange={(event) => setFifoQuantity(Number(event.target.value))}
                className="h-11 w-24 rounded-[10px] border border-border bg-background px-3 text-center text-xl font-semibold focus:outline-none focus:ring-2 focus:ring-primary/30"
                min={0}
              />
              <Button
                variant="outline"
                size="icon"
                onClick={() =>
                  setFifoQuantity((value) =>
                    Math.min(fifoPreview.max || value + 1, value + 1)
                  )
                }
                disabled={fifoPreview.max === 0 || fifoQuantity >= fifoPreview.max}
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>

            <div className="flex flex-wrap justify-center gap-2">
              {fifoChips.map((amount) => (
                <Button
                  key={amount}
                  variant={fifoPreview.quantity === amount ? "primary" : "secondary"}
                  size="sm"
                  onClick={() => setFifoQuantity(amount)}
                >
                  {amount === fifoPreview.max ? "全部" : amount}
                </Button>
              ))}
            </div>

            <BatchNoteControls
              rows={fifoNotes.map((entry) => ({
                clientId: entry.username,
                username: entry.username,
                note: entry.note,
                overwriteNote: entry.overwriteNote,
              }))}
              onRowsChange={(rows) =>
                setFifoNotes(
                  rows.map((row) => ({
                    username: row.username ?? "",
                    note: row.note,
                    overwriteNote: row.overwriteNote,
                  }))
                )
              }
              disabled={fifoBusy}
            />

            <FifoTable
              rows={fifoPreview.rows}
              fifoNotesByUsername={fifoNotesByUsername}
              onFifoNoteChange={updateFifoNote}
            />

            {fifoMessage && (
              <p
                className={cn(
                  "text-sm",
                  fifoMessage.includes("失败") ? "text-red-600" : "text-emerald-600"
                )}
              >
                {fifoMessage}
              </p>
            )}

            <div className="grid gap-2 sm:grid-cols-3">
              <Button
                className="w-full"
                onClick={() => void handleFifoCommit()}
                disabled={fifoBusy || fifoPreview.quantity === 0}
              >
                <Upload className="h-4 w-4" />
                出库并复制 ({fifoPreview.quantity})
              </Button>
              <OutboundCopyButton
                className="w-full"
                clipboardText={fifoClipboardText}
                copying={fifoCopying}
                copied={fifoCopied}
                onCopy={handleFifoCopy}
                disabled={fifoBusy}
              />
              <Button
                className="w-full"
                variant="secondary"
                onClick={() => void handleFifoDownload()}
                disabled={fifoBusy || fifoPreview.quantity === 0}
              >
                <Download className="h-4 w-4" />
                出库并下载 TXT
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="p-4 pb-3 sm:p-6 sm:pb-4">
            <CardTitle className="flex items-center gap-2 text-base">
              FIFO 预览
              <Badge variant="fifo">将按此顺序出库</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 sm:p-6 sm:pt-0">
            <FifoTable rows={dashboard.fifoPreview} mobileLimit={3} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="p-4 pb-3 sm:p-6 sm:pb-4">
            <CardTitle className="text-base">最近活动</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 sm:p-6 sm:pt-0">
            <ActivitiesList activities={dashboard.recentActivities} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
