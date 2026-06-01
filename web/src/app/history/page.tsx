"use client";

import { useMemo, useState } from "react";
import { Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { PasswordField } from "@/components/ui/password-field";
import { mockHistory } from "@/lib/mock-data";
import {
  formatAccountLine,
  formatDateTime,
  groupByDate,
} from "@/lib/utils";

export default function HistoryPage() {
  const [filter, setFilter] = useState("");

  const filtered = useMemo(() => {
    if (!filter) return mockHistory;
    const q = filter.toLowerCase();
    return mockHistory.filter(
      (r) =>
        r.username.toLowerCase().includes(q) ||
        r.email?.toLowerCase().includes(q)
    );
  }, [filter]);

  const groups = useMemo(() => groupByDate(filtered), [filtered]);

  const copyRecord = (r: (typeof mockHistory)[0]) => {
    navigator.clipboard.writeText(
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
            共 {mockHistory.length} 条出库记录
          </p>
        </div>
        <Input
          placeholder="搜索账号或邮箱…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="max-w-xs"
        />
      </div>

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
                              onClick={() => copyRecord(record)}
                            >
                              <Copy className="h-3.5 w-3.5" />
                            </Button>
                            <Button variant="ghost" size="sm" className="text-xs">
                              重新入库
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
