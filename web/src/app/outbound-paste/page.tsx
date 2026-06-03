"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ClipboardPaste,
  Copy,
  Trash2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { BatchNoteControls } from "@/components/notes/batch-note-controls";
import { OutboundNoteField } from "@/components/notes/outbound-note-field";
import { OutboundCopyButton } from "@/components/outbound/outbound-copy-button";
import { useLastOutboundClipboard } from "@/hooks/use-last-outbound-clipboard";
import { commitOutboundPaste, writeAppClipboardText } from "@/lib/api";
import { subscribeDatabaseChanged } from "@/lib/database-events";
import { parseAccountLine, parseLines } from "@/lib/parser";
import { useSeparatorRules } from "@/lib/use-separator-rules";
import { getClipboardWsUrl, isClipboardMessage } from "@/lib/ws";
import { cn, maskValue } from "@/lib/utils";
import type {
  OutboundPasteCategory,
  OutboundPasteRow,
} from "@/types/account";

const DEMO_TEXT = `alpha_user01----Pass@2026a----alpha01@mail.example.com
ghost_user----NotInStock----ghost@test.com
old_user01----OldPass01
bad-format-line
alpha_user01----BatchDup----dup@test.com`;

const CATEGORY_LABELS: Record<OutboundPasteCategory, string> = {
  ready: "待检测",
  inInventory: "库存出库",
  notInInventory: "直接出库",
  inHistory: "已在历史",
  invalid: "格式错误",
  batchDuplicate: "批次内重复",
};

function categoryBadge(category: OutboundPasteCategory) {
  if (category === "ready" || category === "inInventory") return "success";
  if (category === "notInInventory") return "info";
  if (category === "inHistory" || category === "batchDuplicate") return "error";
  return "secondary";
}

function rowTone(row: OutboundPasteRow) {
  if (row.status === "success") return "bg-emerald-50/80 dark:bg-emerald-950/25";
  if (row.status === "error") return "bg-red-50/70 dark:bg-red-950/20";
  if (row.category === "invalid") return "bg-muted/40";
  return "bg-muted/20";
}

function buildDraftRows(text: string, separators: string[]): OutboundPasteRow[] {
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
        reason: "确认出库后统一检测账号状态",
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

function displayMessage(row: OutboundPasteRow) {
  return row.message ?? row.reason ?? "-";
}

export default function OutboundPastePage() {
  const wsTimerRef = useRef<number | null>(null);
  const textRef = useRef("");
  const resultRowsRef = useRef<Map<string, OutboundPasteRow>>(new Map());
  const { enabledSeparators, loading: rulesLoading, error: rulesError } =
    useSeparatorRules();
  const rulesReady = !rulesLoading && !rulesError;
  const [text, setText] = useState("");
  const [draftRows, setDraftRows] = useState<OutboundPasteRow[]>([]);
  const [deletedIds, setDeletedIds] = useState<Set<string>>(new Set());
  const [resultRows, setResultRows] = useState<Map<string, OutboundPasteRow>>(
    new Map()
  );
  const [clipboardState, setClipboardState] = useState("连接剪贴板检测中");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const {
    clipboardText,
    remember,
    clear: clearClipboard,
    copy,
    copying,
    copied,
  } = useLastOutboundClipboard();

  const resetForText = useCallback((value: string) => {
    textRef.current = value;
    resultRowsRef.current = new Map();
    setText(value);
    setDraftRows(rulesReady ? buildDraftRows(value, enabledSeparators) : []);
    setDeletedIds(new Set());
    setResultRows(new Map());
    setMessage("");
    clearClipboard();
  }, [clearClipboard, enabledSeparators, rulesReady]);

  const appendText = useCallback((value: string) => {
    const nextValue = value.trim();
    if (!nextValue) return;
    const currentValue = textRef.current.trimEnd();
    resetForText(currentValue ? `${currentValue}\n${nextValue}` : nextValue);
  }, [resetForText]);

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
          if (resultRowsRef.current.size > 0) resetForText(value.text);
          else appendText(value.text);
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
  }, [appendText, resetForText]);

  useEffect(
    () =>
      subscribeDatabaseChanged(() => {
        resetForText(textRef.current);
        setClipboardState("数据库已切换，请重新确认出库结果");
      }),
    [resetForText]
  );

  useEffect(() => {
    if (!textRef.current || !rulesReady) return;
    setDraftRows(buildDraftRows(textRef.current, enabledSeparators));
  }, [enabledSeparators, rulesReady]);

  function updateDraftRow(clientId: string, patch: Partial<OutboundPasteRow>) {
    setDraftRows((rows) =>
      rows.map((row) => (row.clientId === clientId ? { ...row, ...patch } : row))
    );
  }

  const displayedRows = useMemo(
    () =>
      draftRows
        .filter((row) => !deletedIds.has(row.clientId))
        .map((row) => resultRows.get(row.clientId) ?? row),
    [deletedIds, draftRows, resultRows]
  );

  const counts = useMemo(() => {
    return displayedRows.reduce(
      (acc, row) => {
        acc[row.category] += 1;
        return acc;
      },
      {
        ready: 0,
        inInventory: 0,
        notInInventory: 0,
        inHistory: 0,
        invalid: 0,
        batchDuplicate: 0,
      } as Record<OutboundPasteCategory, number>
    );
  }, [displayedRows]);

  const commitRows = displayedRows
    .filter((row) => !row.status)
    .map((row) => ({
      clientId: row.clientId,
      line: row.line,
      note: row.note,
      overwriteNote: row.overwriteNote,
    }));

  async function handleConfirm() {
    if (commitRows.length === 0) return;
    setBusy(true);
    setMessage("");
    try {
      const payload = await commitOutboundPaste(commitRows);
      const nextRows = new Map(payload.rows.map((row) => [row.clientId, row]));
      resultRowsRef.current = nextRows;
      setResultRows(nextRows);
      const text = payload.clipboardText ?? "";
      remember(text);
      const copiedOk = text ? await copy(text) : true;
      const summary = `出库完成：成功 ${payload.successCount} 条，失败 ${payload.errorCount} 条`;
      setMessage(
        copiedOk
          ? `${summary}，已复制到剪贴板`
          : `${summary}，复制失败请点重新复制`
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "出库提交失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleCopyOutbound() {
    setMessage("");
    const ok = await copy();
    if (!ok && clipboardText) {
      setMessage("复制到剪贴板失败，请重试");
    }
  }

  function copyFailures() {
    const failures = displayedRows
      .filter((row) => row.status === "error" || row.category === "invalid")
      .map((row) => row.line)
      .join("\n");
    if (failures) void writeAppClipboardText(failures);
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">出库粘贴</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          批量粘贴账号，确认后统一检测状态并出库
        </p>
        <p className="mt-1 text-xs text-muted-foreground">{clipboardState}</p>
        {rulesLoading && (
          <p className="mt-1 text-xs text-muted-foreground">加载分隔规则中…</p>
        )}
        {rulesError && (
          <p className="mt-1 text-xs text-red-600">{rulesError}</p>
        )}
      </div>

      <Card>
        <CardHeader className="gap-3 sm:flex-row sm:items-center sm:justify-between sm:space-y-0">
          <CardTitle className="text-base">粘贴区</CardTitle>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigator.clipboard.readText().then(resetForText)}
            >
              <ClipboardPaste className="h-4 w-4" />
              从剪贴板粘贴
            </Button>
            <Button variant="ghost" size="sm" onClick={() => resetForText("")}>
              <Trash2 className="h-4 w-4" />
              清空
            </Button>
            <Button variant="ghost" size="sm" onClick={() => resetForText(DEMO_TEXT)}>
              演示数据
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            value={text}
            onChange={(event) => resetForText(event.target.value)}
            placeholder="使用已启用分隔规则，示例：账号----密码----邮箱----邮箱密码----网址"
            className="min-h-[180px] font-mono text-xs"
          />

          <div className="flex flex-wrap gap-2">
            {(Object.keys(CATEGORY_LABELS) as OutboundPasteCategory[]).map(
              (category) => (
                <Badge key={category} variant={categoryBadge(category)}>
                  {CATEGORY_LABELS[category]} {counts[category]}
                </Badge>
              )
            )}
          </div>

          <BatchNoteControls
            rows={draftRows}
            onRowsChange={setDraftRows}
            disabled={busy || rulesLoading || !!rulesError}
          />

          <div className="hidden overflow-x-auto rounded-xl border border-border md:block">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40">
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
                    <td colSpan={8} className="px-3 py-8 text-center text-muted-foreground">
                      输入账号文本后会转换为表格
                    </td>
                  </tr>
                ) : (
                  displayedRows.map((row) => (
                    <tr
                      key={row.clientId}
                      className={cn("border-b border-border last:border-0", rowTone(row))}
                    >
                      <td className="px-3 py-2.5">
                        <Badge variant={categoryBadge(row.category)}>
                          {CATEGORY_LABELS[row.category]}
                        </Badge>
                      </td>
                      <td className="px-3 py-2.5 font-mono text-xs">
                        {row.username ?? row.line}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-xs">
                        {row.password ? maskValue(row.password) : "-"}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-xs">
                        {row.email ?? "-"}
                      </td>
                      <td className="max-w-[220px] truncate px-3 py-2.5 font-mono text-xs">
                        {row.url ?? "-"}
                      </td>
                      <td className="min-w-[140px] px-3 py-2.5">
                        <OutboundNoteField
                          value={row.note ?? ""}
                          onChange={(note) =>
                            updateDraftRow(row.clientId, {
                              note,
                              overwriteNote: false,
                            })
                          }
                          overwriteNote={row.overwriteNote ?? false}
                          onOverwriteNoteChange={(overwriteNote) =>
                            updateDraftRow(row.clientId, { overwriteNote })
                          }
                          disabled={row.status === "success"}
                          inputClassName="h-8 text-xs"
                        />
                      </td>
                      <td className="px-3 py-2.5 text-xs text-muted-foreground">
                        {displayMessage(row)}
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
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="space-y-2 md:hidden">
            {displayedRows.length === 0 ? (
              <p className="rounded-xl border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
                输入账号文本后会转换为表格
              </p>
            ) : (
              displayedRows.map((row) => (
                <div
                  key={`${row.clientId}-mobile`}
                  className={cn(
                    "rounded-xl border border-border p-3",
                    rowTone(row)
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <Badge variant={categoryBadge(row.category)}>
                          {CATEGORY_LABELS[row.category]}
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
                        {row.email && (
                          <p className="truncate font-mono">{row.email}</p>
                        )}
                        {row.url && (
                          <p className="break-all font-mono">{row.url}</p>
                        )}
                        <OutboundNoteField
                          value={row.note ?? ""}
                          onChange={(note) =>
                            updateDraftRow(row.clientId, {
                              note,
                              overwriteNote: false,
                            })
                          }
                          overwriteNote={row.overwriteNote ?? false}
                          onOverwriteNoteChange={(overwriteNote) =>
                            updateDraftRow(row.clientId, { overwriteNote })
                          }
                          disabled={row.status === "success"}
                          className="mt-2 w-full"
                          inputClassName="h-8 w-full text-xs"
                        />
                        <p className="break-words whitespace-pre-wrap">
                          {displayMessage(row)}
                        </p>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="shrink-0"
                      onClick={() =>
                        setDeletedIds((prev) => new Set(prev).add(row.clientId))
                      }
                      aria-label="删除条目"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-card p-4 shadow-sm">
        <Button
          onClick={handleConfirm}
          disabled={busy || commitRows.length === 0 || rulesLoading || !!rulesError}
        >
          <Check className="h-4 w-4" />
          确认出库并复制 ({commitRows.length})
        </Button>
        <OutboundCopyButton
          variant="outline"
          clipboardText={clipboardText}
          copying={copying}
          copied={copied}
          onCopy={handleCopyOutbound}
          disabled={busy}
        />
        <Button variant="outline" onClick={copyFailures} disabled={displayedRows.length === 0}>
          <Copy className="h-4 w-4" />
          复制失败行
        </Button>
        {message && <span className="text-sm text-muted-foreground">{message}</span>}
      </div>
    </div>
  );
}
