"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { PasswordField } from "@/components/ui/password-field";
import { fetchOutboundHistory, writeAppClipboardText } from "@/lib/api";
import { subscribeDatabaseChanged } from "@/lib/database-events";
import type { OutboundRecord } from "@/types/account";
import {
  formatAccountLine,
  formatDateTime,
  groupByDate,
} from "@/lib/utils";

export default function HistoryPage() {
  const [filter, setFilter] = useState("");
  const [records, setRecords] = useState<OutboundRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const payload = await fetchOutboundHistory();
      setRecords(payload);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "出库历史读取失败"
      );
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    fetchOutboundHistory()
      .then((payload) => {
        if (!active) return;
        setRecords(payload);
      })
      .catch((requestError) => {
        if (!active) return;
        setError(
          requestError instanceof Error ? requestError.message : "出库历史读取失败"
        );
        setRecords([]);
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(
    () => subscribeDatabaseChanged(() => void loadHistory()),
    [loadHistory]
  );

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return records;
    return records.filter(
      (r) =>
        r.username.toLowerCase().includes(q) ||
        r.email?.toLowerCase().includes(q)
    );
  }, [filter, records]);

  const groups = useMemo(() => groupByDate(filtered), [filtered]);

  const copyRecord = (r: OutboundRecord) => {
    void writeAppClipboardText(
      formatAccountLine(
        r.username,
        r.password,
        r.email,
        r.emailPassword,
        r.url
      )
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">出库历史</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            共 {records.length} 条出库记录
          </p>
        </div>
        <Input
          placeholder="搜索账号或邮箱…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="max-w-xs"
        />
      </div>

      {loading && (
        <Card>
          <CardContent className="py-8 text-sm text-muted-foreground">
            正在加载出库历史...
          </CardContent>
        </Card>
      )}

      {!loading && error && (
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-6">
            <p className="text-sm text-red-600">出库历史读取失败：{error}</p>
            <Button variant="outline" size="sm" onClick={() => void loadHistory()}>
              重试
            </Button>
          </CardContent>
        </Card>
      )}

      {!loading && !error && records.length === 0 && (
        <Card>
          <CardContent className="py-8 text-sm text-muted-foreground">
            暂无出库历史记录
          </CardContent>
        </Card>
      )}

      {!loading && !error && records.length > 0 && filtered.length === 0 && (
        <Card>
          <CardContent className="py-8 text-sm text-muted-foreground">
            没有匹配的出库历史记录
          </CardContent>
        </Card>
      )}

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
                      <th className="px-4 py-3 text-left font-medium">账号</th>
                      <th className="px-4 py-3 text-left font-medium">密码</th>
                      <th className="px-4 py-3 text-left font-medium">邮箱</th>
                      <th className="px-4 py-3 text-left font-medium">入库时间</th>
                      <th className="px-4 py-3 text-left font-medium">出库时间</th>
                      <th className="px-4 py-3 text-left font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.items.map((record) => (
                      <tr
                        key={record.id}
                        className="border-b border-border last:border-0 hover:bg-muted/30"
                      >
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
                          {formatDateTime(record.inboundAt)}
                        </td>
                        <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
                          {formatDateTime(record.outboundAt)}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex gap-1">
                            <Button
                              variant="ghost"
                              size="icon"
                              title="复制"
                              onClick={() => copyRecord(record)}
                            >
                              <Copy className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      ))}
    </div>
  );
}
