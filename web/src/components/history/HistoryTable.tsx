"use client";

import { useMemo, useState } from "react";
import { Copy, Download } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  AccountColumnHeader,
  AccountFieldCell,
  OUTBOUND_RECORD_COLUMNS,
} from "@/lib/account-columns";
import { exportHistoryText } from "@/lib/api";
import {
  type HistoryManualCopyKind,
  resolveHistoryManualCopyRetry,
  runAppClipboardCopy,
  historyQuickActionRowError,
} from "@/lib/clipboard-actions";
import { ClipboardCopyError } from "@/lib/clipboard";
import { ClipboardCopyFallback } from "@/components/clipboard/clipboard-copy-fallback";
import {
  defaultHistoryTextFilename,
  downloadTextFile,
} from "@/lib/download";
import {
  formatDateTime,
  formatHistoryRecordLine,
  groupByDate,
} from "@/lib/utils";
import type { HistoryRecord, InboundRecord, OutboundRecord } from "@/types/account";

type HistoryTableMode = "all" | "inbound" | "outbound";

export interface HistoryExportFilters {
  type?: "all" | "inbound" | "outbound";
  q?: string;
  ranges?: string[];
}

interface HistoryTableProps {
  mode: HistoryTableMode;
  exportMode?: HistoryTableMode;
  records: HistoryRecord[] | InboundRecord[] | OutboundRecord[];
  total: number;
  exportFilters: HistoryExportFilters;
  loading?: boolean;
  error?: string;
  emptyMessage?: string;
  onRetry?: () => void;
  inventoryUsernames?: Set<string>;
  onReInbound?: (record: OutboundRecord | HistoryRecord) => Promise<void>;
  onOutboundFromInbound?: (
    record: InboundRecord | HistoryRecord
  ) => Promise<void>;
}

type HistoryCopyRecord = Parameters<typeof formatHistoryRecordLine>[0];

async function copyLine(
  record: HistoryCopyRecord,
  onFailure: (text: string, reason: string) => void,
  onSuccess: () => void
) {
  const text = formatHistoryRecordLine(record);
  const outcome = await runAppClipboardCopy(text);
  if (!outcome.ok) {
    onFailure(
      outcome.manualCopyText ?? text,
      outcome.reason ?? "复制失败"
    );
    return;
  }
  onSuccess();
}

function isHistoryRecord(
  record: HistoryRecord | InboundRecord | OutboundRecord
): record is HistoryRecord {
  return "type" in record && "timestamp" in record;
}

function isOutboundRecord(
  record: HistoryRecord | InboundRecord | OutboundRecord
): record is OutboundRecord {
  return "outboundAt" in record;
}

function isInboundHistoryRecord(
  record: HistoryRecord | InboundRecord | OutboundRecord
): record is InboundRecord | HistoryRecord {
  if (modeIsInboundOnly(record)) return true;
  return isHistoryRecord(record) && record.type === "inbound";
}

function modeIsInboundOnly(
  record: HistoryRecord | InboundRecord | OutboundRecord
): record is InboundRecord {
  return "inboundAt" in record && !("outboundAt" in record) && !("type" in record);
}

function canReInbound(
  record: HistoryRecord | InboundRecord | OutboundRecord,
  mode: HistoryTableMode,
  onReInbound?: HistoryTableProps["onReInbound"]
): record is OutboundRecord | HistoryRecord {
  if (!onReInbound || mode === "inbound") return false;
  if (mode === "outbound") return true;
  return isHistoryRecord(record) && record.type === "outbound";
}

function canOutboundFromInbound(
  record: HistoryRecord | InboundRecord | OutboundRecord,
  mode: HistoryTableMode,
  onOutboundFromInbound?: HistoryTableProps["onOutboundFromInbound"]
): record is InboundRecord | HistoryRecord {
  if (!onOutboundFromInbound || mode === "outbound") return false;
  if (mode === "inbound") return true;
  return isHistoryRecord(record) && record.type === "inbound";
}

function recordHasOutbound(
  record: InboundRecord | HistoryRecord
): boolean {
  return Boolean(record.hasOutbound);
}

function RowActions({
  record,
  mode,
  inventoryUsernames,
  onReInbound,
  onOutboundFromInbound,
  busyId,
  rowErrors,
  onReInboundClick,
  onOutboundFromInboundClick,
  onCopyFailure,
  onCopySuccess,
}: {
  record: HistoryRecord | InboundRecord | OutboundRecord;
  mode: HistoryTableMode;
  inventoryUsernames?: Set<string>;
  onReInbound?: HistoryTableProps["onReInbound"];
  onOutboundFromInbound?: HistoryTableProps["onOutboundFromInbound"];
  busyId: string | null;
  rowErrors: Record<string, string>;
  onReInboundClick: (record: OutboundRecord | HistoryRecord) => void;
  onOutboundFromInboundClick: (record: InboundRecord | HistoryRecord) => void;
  onCopyFailure: (text: string, reason: string) => void;
  onCopySuccess: () => void;
}) {
  const showReInbound = canReInbound(record, mode, onReInbound);
  const showOutboundFromInbound = canOutboundFromInbound(
    record,
    mode,
    onOutboundFromInbound
  );
  const inInventory = inventoryUsernames?.has(record.username) ?? false;
  const hasOutbound =
    showOutboundFromInbound && isInboundHistoryRecord(record)
      ? recordHasOutbound(record)
      : false;
  const isBusy = busyId === record.id;
  const rowError = rowErrors[record.id];

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1 whitespace-nowrap">
        {showReInbound && (
          <Button
            variant="secondary"
            size="sm"
            className="h-8 px-2 text-xs"
            disabled={inInventory || isBusy || Boolean(busyId)}
            title={inInventory ? "已在库存" : undefined}
            onClick={() => onReInboundClick(record)}
          >
            {isBusy ? "入库中…" : "入库"}
          </Button>
        )}
        {showOutboundFromInbound && (
          <Button
            variant="secondary"
            size="sm"
            className="h-8 px-2 text-xs"
            disabled={hasOutbound || isBusy || Boolean(busyId)}
            title={hasOutbound ? "该入库记录已出库" : undefined}
            onClick={() => onOutboundFromInboundClick(record)}
          >
            {isBusy ? "出库中…" : "出库"}
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          title="复制"
          disabled={Boolean(busyId) && busyId !== record.id}
          onClick={() => void copyLine(record, onCopyFailure, onCopySuccess)}
        >
          <Copy className="h-3.5 w-3.5" />
        </Button>
      </div>
      {rowError && (
        <p className="max-w-[140px] text-xs text-red-600">{rowError}</p>
      )}
    </div>
  );
}

export function HistoryTable({
  mode,
  exportMode,
  records,
  total,
  exportFilters,
  loading = false,
  error = "",
  emptyMessage = "暂无历史记录",
  onRetry,
  inventoryUsernames,
  onReInbound,
  onOutboundFromInbound,
}: HistoryTableProps) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [exportBusy, setExportBusy] = useState(false);
  const [exportError, setExportError] = useState("");
  const [manualCopy, setManualCopy] = useState<{
    text: string;
    reason?: string;
    kind: HistoryManualCopyKind;
    onRetry: () => void | Promise<void>;
  } | null>(null);

  function clearManualCopy() {
    setManualCopy(null);
  }

  function buildManualCopyRetry(
    kind: HistoryManualCopyKind,
    text: string
  ): () => void | Promise<void> {
    return resolveHistoryManualCopyRetry({
      kind,
      text,
      retryTextCopy: retryCopyText,
      retryExportAll: copyAll,
    });
  }

  async function retryCopyText(text: string) {
    const outcome = await runAppClipboardCopy(text);
    if (outcome.ok) {
      clearManualCopy();
      setExportError("");
      return;
    }
    const failedText = outcome.manualCopyText ?? text;
    setManualCopy((current) => {
      if (!current) return null;
      return {
        text: failedText,
        reason: outcome.reason ?? current.reason ?? "复制失败",
        kind: current.kind,
        onRetry: buildManualCopyRetry(current.kind, failedText),
      };
    });
  }

  function registerCopyFailure(
    text: string,
    reason: string | undefined,
    kind: HistoryManualCopyKind
  ) {
    setManualCopy({
      text,
      reason,
      kind,
      onRetry: buildManualCopyRetry(kind, text),
    });
  }

  const filenameMode = exportMode ?? mode;
  const bulkDisabled = loading || exportBusy || total === 0;
  const exportCount = total;

  async function handleReInboundClick(record: OutboundRecord | HistoryRecord) {
    if (!onReInbound || busyId) return;
    setBusyId(record.id);
    setRowErrors((current) => {
      const next = { ...current };
      delete next[record.id];
      return next;
    });
    try {
      await onReInbound(record);
      clearManualCopy();
    } catch (err) {
      if (err instanceof ClipboardCopyError) {
        registerCopyFailure(err.text, err.reason, "quick-action");
      }
      setRowErrors((current) => ({
        ...current,
        [record.id]: historyQuickActionRowError(err, "入库失败"),
      }));
    } finally {
      setBusyId(null);
    }
  }

  async function handleOutboundFromInboundClick(
    record: InboundRecord | HistoryRecord
  ) {
    if (!onOutboundFromInbound || busyId) return;
    setBusyId(record.id);
    setRowErrors((current) => {
      const next = { ...current };
      delete next[record.id];
      return next;
    });
    try {
      await onOutboundFromInbound(record);
      clearManualCopy();
    } catch (err) {
      if (err instanceof ClipboardCopyError) {
        registerCopyFailure(err.text, err.reason, "quick-action");
      }
      setRowErrors((current) => ({
        ...current,
        [record.id]: historyQuickActionRowError(err, "出库失败"),
      }));
    } finally {
      setBusyId(null);
    }
  }

  async function fetchExportText() {
    const payload = await exportHistoryText({
      type: exportFilters.type ?? filenameMode,
      q: exportFilters.q,
      ranges: exportFilters.ranges,
    });
    return payload.text;
  }

  async function copyAll() {
    setExportError("");
    setExportBusy(true);
    try {
      const text = await fetchExportText();
      const outcome = await runAppClipboardCopy(text);
      if (!outcome.ok) {
        const failedText = outcome.manualCopyText ?? text;
        registerCopyFailure(
          failedText,
          outcome.reason ?? "复制失败",
          "export-all"
        );
        setExportError(outcome.reason ?? "复制失败");
      } else {
        clearManualCopy();
      }
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "复制失败");
    } finally {
      setExportBusy(false);
    }
  }

  async function exportAll() {
    setExportError("");
    setExportBusy(true);
    try {
      const text = await fetchExportText();
      downloadTextFile(text, defaultHistoryTextFilename(filenameMode));
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "导出失败");
      console.error("导出失败", err);
    } finally {
      setExportBusy(false);
    }
  }

  const tableColumns = useMemo(
    () =>
      OUTBOUND_RECORD_COLUMNS.filter(
        (column) =>
          column.key !== "outboundAt" || mode === "outbound" || mode === "all"
      ),
    [mode]
  );

  const groups =
    mode === "all"
      ? groupByDate(records as HistoryRecord[], "timestamp")
      : mode === "outbound"
        ? groupByDate(records as OutboundRecord[], "outboundAt")
        : groupByDate(records as InboundRecord[], "inboundAt");

  if (loading) {
    return (
      <Card>
        <CardContent className="py-8 text-sm text-muted-foreground">
          正在加载历史记录...
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 py-6">
          <p className="text-sm text-red-600">历史记录读取失败：{error}</p>
          {onRetry && (
            <Button variant="outline" size="sm" onClick={onRetry}>
              重试
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  if (records.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-sm text-muted-foreground">
          {emptyMessage}
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          disabled={bulkDisabled}
          onClick={() => void copyAll()}
        >
          <Copy className="h-4 w-4" />
          {exportBusy ? "处理中…" : `复制全部 (${exportCount})`}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={bulkDisabled}
          onClick={() => void exportAll()}
        >
          <Download className="h-4 w-4" />
          {exportBusy ? "处理中…" : `导出 TXT (${exportCount})`}
        </Button>
        {exportError && (
          <p className="text-sm text-red-600">{exportError}</p>
        )}
      </div>
      <ClipboardCopyFallback
        visible={Boolean(manualCopy?.text)}
        text={manualCopy?.text ?? ""}
        reason={manualCopy?.reason}
        onRetry={() => void manualCopy?.onRetry()}
        onCopied={clearManualCopy}
      />
      {groups.map((group) => (
        <div key={group.label} className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground">
            {group.label}
          </h2>
          <Card>
            <CardContent className="p-0">
              <div className="hidden overflow-x-auto md:block">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-muted/40">
                      <th className="px-2 py-3 text-left font-medium whitespace-nowrap">
                        操作
                      </th>
                      {mode === "all" && (
                        <th className="px-4 py-3 text-left font-medium">类型</th>
                      )}
                      <th className="px-4 py-3 text-left font-medium">账号</th>
                      {tableColumns.slice(1).map((column) => (
                        <AccountColumnHeader key={column.key} column={column} />
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {group.items.map((record) => {
                      const history = isHistoryRecord(record) ? record : null;
                      return (
                        <tr
                          key={record.id}
                          className="border-b border-border last:border-0 hover:bg-muted/30"
                        >
                          <td className="px-2 py-3">
                            <RowActions
                              record={record}
                              mode={mode}
                              inventoryUsernames={inventoryUsernames}
                              onReInbound={onReInbound}
                              onOutboundFromInbound={onOutboundFromInbound}
                              busyId={busyId}
                              rowErrors={rowErrors}
                              onReInboundClick={handleReInboundClick}
                              onOutboundFromInboundClick={
                                handleOutboundFromInboundClick
                              }
                              onCopyFailure={(text, reason) =>
                                registerCopyFailure(text, reason, "line")
                              }
                              onCopySuccess={clearManualCopy}
                            />
                          </td>
                          {mode === "all" && history && (
                            <td className="px-4 py-3">
                              <Badge
                                variant={
                                  history.type === "inbound" ? "inventory" : "history"
                                }
                              >
                                {history.type === "inbound" ? "入库" : "出库"}
                              </Badge>
                            </td>
                          )}
                          <td className="px-4 py-3 font-mono">{record.username}</td>
                          {tableColumns.slice(1).map((column) => (
                            <td key={column.key} className="px-4 py-3">
                              <AccountFieldCell column={column} record={record} />
                            </td>
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="space-y-2 p-3 md:hidden">
                {group.items.map((record) => {
                  const history = isHistoryRecord(record) ? record : null;
                  const outbound = isOutboundRecord(record) ? record : null;
                  return (
                    <div
                      key={`${record.id}-mobile`}
                      className="rounded-xl border border-border p-3"
                    >
                      <div className="flex items-start gap-2">
                        <RowActions
                          record={record}
                          mode={mode}
                          inventoryUsernames={inventoryUsernames}
                          onReInbound={onReInbound}
                          onOutboundFromInbound={onOutboundFromInbound}
                          busyId={busyId}
                          rowErrors={rowErrors}
                          onReInboundClick={handleReInboundClick}
                          onOutboundFromInboundClick={
                            handleOutboundFromInboundClick
                          }
                          onCopyFailure={(text, reason) =>
                            registerCopyFailure(text, reason, "line")
                          }
                          onCopySuccess={clearManualCopy}
                        />
                        <div className="min-w-0 flex-1 space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            {mode === "all" && history && (
                              <Badge
                                variant={
                                  history.type === "inbound" ? "inventory" : "history"
                                }
                              >
                                {history.type === "inbound" ? "入库" : "出库"}
                              </Badge>
                            )}
                            <span className="font-mono text-sm font-medium">
                              {record.username}
                            </span>
                          </div>
                          {tableColumns.slice(1).map((column) => {
                            if (column.key === "password") {
                              return (
                                <div key={column.key}>
                                  <AccountFieldCell column={column} record={record} />
                                </div>
                              );
                            }
                            if (column.key === "note") {
                              return record.note?.trim() ? (
                                <p
                                  key={column.key}
                                  className="break-words whitespace-pre-wrap text-xs text-muted-foreground"
                                >
                                  备注：{record.note}
                                </p>
                              ) : null;
                            }
                            const value = record[column.key as keyof typeof record];
                            if (!value) return null;
                            return (
                              <div key={column.key} className="text-xs text-muted-foreground">
                                {column.label}{" "}
                                {column.kind === "password" ? (
                                  <AccountFieldCell column={column} record={record} />
                                ) : column.kind === "datetime" ? (
                                  formatDateTime(String(value))
                                ) : (
                                  String(value)
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </div>
      ))}
    </>
  );
}
