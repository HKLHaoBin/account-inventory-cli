"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ClipboardPaste,
  Copy,
  FileText,
  Trash2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { commitInbound, writeAppClipboardText } from "@/lib/api";
import { parseAccountLine, parseLines } from "@/lib/parser";
import { getClipboardWsUrl, isClipboardMessage } from "@/lib/ws";
import { cn, formatDateTime, maskValue } from "@/lib/utils";
import { SAMPLE_FORMAT } from "@/lib/mock-data";
import type {
  InboundCategory,
  InboundCommitResultRow,
  InboundPreviewRow,
} from "@/types/account";

const DEMO_TEXT = `new_user_a----PassA123----newa@mail.com----MailA----https://new.example.com
alpha_user01----DupPass----dup@test.com
returned_user----ReturnPass----ret@test.com----RetMail
badline-only-one-field
new_user_b----PassB456
returned_user----BatchDup----dup2@test.com`;

const CATEGORY_LABELS: Record<InboundCategory, string> = {
  ready: "待检测",
  duplicate: "库存重复",
  pending: "曾出库待确认",
  invalid: "格式错误",
  batchDuplicate: "批次内重复",
};

function categoryBadge(category: InboundCategory) {
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
    if (row.status === "error") return "bg-red-50/80 dark:bg-red-950/20";
  }
  if (row.category === "invalid") return "bg-muted/40";
  return "bg-muted/20";
}

function buildDraftRows(text: string): InboundPreviewRow[] {
  return parseLines(text).map((line, index) => {
    const clientId = `line-${index + 1}`;
    try {
      const account = parseAccountLine(line);
      return {
        clientId,
        line,
        username: account.username,
        password: account.password,
        email: account.email,
        emailPassword: account.emailPassword,
        url: account.url,
        category: "ready",
        reason: "确认入库后统一检测账号状态",
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

function displayMessage(row: InboundPreviewRow | InboundCommitResultRow) {
  if (isCommitResult(row)) return row.message;
  if (row.lastOutboundAt) return `最近出库：${formatDateTime(row.lastOutboundAt)}`;
  return row.reason ?? "-";
}

export default function InboundPage() {
  const wsTimerRef = useRef<number | null>(null);
  const textRef = useRef("");
  const resultRowsRef = useRef<Map<string, InboundCommitResultRow>>(new Map());
  const [text, setText] = useState("");
  const [draftRows, setDraftRows] = useState<InboundPreviewRow[]>([]);
  const [deletedIds, setDeletedIds] = useState<Set<string>>(new Set());
  const [approvedPendingIds, setApprovedPendingIds] = useState<Set<string>>(
    new Set()
  );
  const [resultRows, setResultRows] = useState<Map<string, InboundCommitResultRow>>(
    new Map()
  );
  const [clipboardState, setClipboardState] = useState("连接剪贴板检测中");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const resetForText = useCallback((value: string) => {
    textRef.current = value;
    resultRowsRef.current = new Map();
    setText(value);
    setDraftRows(buildDraftRows(value));
    setDeletedIds(new Set());
    setApprovedPendingIds(new Set());
    setResultRows(new Map());
    setMessage("");
  }, []);

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
        duplicate: 0,
        pending: 0,
        invalid: 0,
        batchDuplicate: 0,
      } as Record<InboundCategory, number>
    );
  }, [displayedRows]);

  const commitRows = displayedRows
    .filter((row) => !isCommitResult(row) || row.status === "warning")
    .map((row) => ({ clientId: row.clientId, line: row.line }));
  const approvedCount = counts.ready + approvedPendingIds.size;

  async function handleConfirm() {
    if (commitRows.length === 0) return;
    setBusy(true);
    setMessage("");
    try {
      const payload = await commitInbound(commitRows, Array.from(approvedPendingIds));
      const nextRows = new Map(payload.rows.map((row) => [row.clientId, row]));
      resultRowsRef.current = nextRows;
      setResultRows(nextRows);
      setMessage(
        `入库完成：成功 ${payload.successCount} 条，失败 ${payload.errorCount} 条，待确认 ${payload.warningCount} 条`
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "入库提交失败");
    } finally {
      setBusy(false);
    }
  }

  function copyFailures() {
    const failures = displayedRows
      .filter(
        (row) =>
          row.category === "invalid" ||
          row.category === "duplicate" ||
          row.category === "batchDuplicate" ||
          (isCommitResult(row) && row.status === "error")
      )
      .map((row) => row.line)
      .join("\n");
    if (failures) void writeAppClipboardText(failures);
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">入库</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          粘贴多行账号，确认后统一检测库存和出库历史
        </p>
        <p className="mt-1 text-xs text-muted-foreground">{clipboardState}</p>
      </div>

      <Card>
        <CardHeader className="gap-3 sm:flex-row sm:items-center sm:justify-between sm:space-y-0">
          <CardTitle className="text-base">输入区</CardTitle>
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
            <Button variant="ghost" size="sm" onClick={() => resetForText(SAMPLE_FORMAT)}>
              <FileText className="h-4 w-4" />
              示例格式
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
            placeholder="粘贴账号行，每行一条&#10;格式：账号----密码----邮箱----邮箱密码----网址"
            className="min-h-[180px] font-mono text-xs"
          />

          <div className="flex flex-wrap gap-2">
            {(Object.keys(CATEGORY_LABELS) as InboundCategory[]).map((category) => (
              <Badge key={category} variant={categoryBadge(category)}>
                {CATEGORY_LABELS[category]} {counts[category]}
              </Badge>
            ))}
          </div>

          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40">
                  <th className="w-10 px-3 py-2.5 text-left font-medium">确认</th>
                  <th className="px-3 py-2.5 text-left font-medium">状态</th>
                  <th className="px-3 py-2.5 text-left font-medium">账号</th>
                  <th className="px-3 py-2.5 text-left font-medium">密码</th>
                  <th className="px-3 py-2.5 text-left font-medium">邮箱</th>
                  <th className="px-3 py-2.5 text-left font-medium">网址</th>
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
                        {row.category === "pending" ? (
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
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-card p-4 shadow-sm">
        <Button onClick={handleConfirm} disabled={busy || commitRows.length === 0}>
          <Check className="h-4 w-4" />
          确认入库 ({approvedCount})
        </Button>
        <Button variant="outline" onClick={copyFailures} disabled={displayedRows.length === 0}>
          <Copy className="h-4 w-4" />
          复制失败行
        </Button>
        {message && <span className="text-sm text-muted-foreground">{message}</span>}
      </div>
    </div>
  );
}
