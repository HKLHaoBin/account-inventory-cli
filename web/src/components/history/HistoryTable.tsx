"use client";

import { Copy } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PasswordField } from "@/components/ui/password-field";
import { writeAppClipboardText } from "@/lib/api";
import {
  formatAccountLine,
  formatDateTime,
  groupByDate,
} from "@/lib/utils";
import type { HistoryRecord, InboundRecord, OutboundRecord } from "@/types/account";

type HistoryTableMode = "all" | "inbound" | "outbound";

interface HistoryTableProps {
  mode: HistoryTableMode;
  records: HistoryRecord[] | InboundRecord[] | OutboundRecord[];
  loading?: boolean;
  error?: string;
  emptyMessage?: string;
  onRetry?: () => void;
}

function copyLine(record: {
  username: string;
  password: string;
  email?: string;
  emailPassword?: string;
  url?: string;
}) {
  void writeAppClipboardText(
    formatAccountLine(
      record.username,
      record.password,
      record.email,
      record.emailPassword,
      record.url
    )
  );
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

export function HistoryTable({
  mode,
  records,
  loading = false,
  error = "",
  emptyMessage = "暂无历史记录",
  onRetry,
}: HistoryTableProps) {
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
      {groups.map((group) => (
        <div key={group.label} className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground">
            {group.label}
          </h2>
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-muted/40">
                      {mode === "all" && (
                        <th className="px-4 py-3 text-left font-medium">类型</th>
                      )}
                      <th className="px-4 py-3 text-left font-medium">账号</th>
                      <th className="px-4 py-3 text-left font-medium">密码</th>
                      <th className="px-4 py-3 text-left font-medium">邮箱</th>
                      <th className="px-4 py-3 text-left font-medium">入库时间</th>
                      {(mode === "outbound" || mode === "all") && (
                        <th className="px-4 py-3 text-left font-medium">出库时间</th>
                      )}
                      <th className="px-4 py-3 text-left font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.items.map((record) => {
                      const history = isHistoryRecord(record) ? record : null;
                      const outbound = isOutboundRecord(record) ? record : null;
                      return (
                        <tr
                          key={record.id}
                          className="border-b border-border last:border-0 hover:bg-muted/30"
                        >
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
                          <td className="px-4 py-3">
                            <PasswordField value={record.password} />
                          </td>
                          <td className="px-4 py-3">
                            {record.email ? (
                              <span className="text-xs">{record.email}</span>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
                            {record.inboundAt ? (
                              formatDateTime(record.inboundAt)
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </td>
                          {(mode === "outbound" || mode === "all") && (
                            <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
                              {outbound?.outboundAt || history?.outboundAt ? (
                                formatDateTime(
                                  outbound?.outboundAt ?? history?.outboundAt ?? ""
                                )
                              ) : (
                                <span className="text-muted-foreground">—</span>
                              )}
                            </td>
                          )}
                          <td className="px-4 py-3">
                            <Button
                              variant="ghost"
                              size="icon"
                              title="复制"
                              onClick={() => copyLine(record)}
                            >
                              <Copy className="h-3.5 w-3.5" />
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      ))}
    </>
  );
}
