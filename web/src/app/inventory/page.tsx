"use client";

import { useMemo, useState } from "react";
import {
  ArrowUpDown,
  Copy,
  Upload,
  CheckSquare,
  Square,
  PackageOpen,
} from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { PasswordField } from "@/components/ui/password-field";
import { mockInventory } from "@/lib/mock-data";
import {
  cn,
  formatAccountLine,
  formatDateTime,
} from "@/lib/utils";
import type { Account } from "@/types/account";

type SortKey = "inboundAt" | "username";
type SortDir = "asc" | "desc";

export default function InventoryPage() {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("inboundAt");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [density, setDensity] = useState<"comfortable" | "compact">(
    "comfortable"
  );

  const sorted = useMemo(() => {
    let items = [...mockInventory];
    if (filter) {
      const q = filter.toLowerCase();
      items = items.filter(
        (a) =>
          a.username.toLowerCase().includes(q) ||
          a.email?.toLowerCase().includes(q)
      );
    }
    items.sort((a, b) => {
      const av = sortKey === "inboundAt" ? a.inboundAt : a.username;
      const bv = sortKey === "inboundAt" ? b.inboundAt : b.username;
      const cmp = av.localeCompare(bv);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return items;
  }, [filter, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === sorted.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(sorted.map((a) => a.id)));
    }
  };

  const copyAccount = (a: Account) => {
    navigator.clipboard.writeText(
      formatAccountLine(
        a.username,
        a.password,
        a.email,
        a.emailPassword,
        a.url
      )
    );
  };

  const rowPadding = density === "compact" ? "py-2" : "py-3.5";

  if (mockInventory.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <PackageOpen className="h-12 w-12 text-muted-foreground" />
        <p className="mt-4 text-lg font-medium">库存为空</p>
        <Link href="/inbound">
          <Button className="mt-4">去入库</Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">库存列表</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            共 {mockInventory.length} 条 · 默认按 FIFO 入库时间排序
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="本页过滤…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="max-w-xs"
        />
        <Button
          variant="secondary"
          size="sm"
          onClick={() => toggleSort("inboundAt")}
        >
          <ArrowUpDown className="h-4 w-4" />
          入库时间 {sortKey === "inboundAt" && (sortDir === "asc" ? "↑" : "↓")}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => toggleSort("username")}
        >
          账号 {sortKey === "username" && (sortDir === "asc" ? "↑" : "↓")}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={selected.size === 0}
        >
          <Upload className="h-4 w-4" />
          出库选中 ({selected.size})
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={selected.size === 0}
          onClick={() => {
            const lines = sorted
              .filter((a) => selected.has(a.id))
              .map((a) =>
                formatAccountLine(
                  a.username,
                  a.password,
                  a.email,
                  a.emailPassword,
                  a.url
                )
              )
              .join("\n");
            navigator.clipboard.writeText(lines);
          }}
        >
          <Copy className="h-4 w-4" />
          复制选中
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() =>
            setDensity((d) => (d === "comfortable" ? "compact" : "comfortable"))
          }
        >
          {density === "comfortable" ? "紧凑" : "舒适"}
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40">
                  <th className="w-10 px-4 py-3">
                    <button type="button" onClick={toggleAll}>
                      {selected.size === sorted.length && sorted.length > 0 ? (
                        <CheckSquare className="h-4 w-4 text-primary" />
                      ) : (
                        <Square className="h-4 w-4 text-muted-foreground" />
                      )}
                    </button>
                  </th>
                  <th className="px-4 py-3 text-left font-medium">账号</th>
                  <th className="px-4 py-3 text-left font-medium">密码</th>
                  <th className="px-4 py-3 text-left font-medium">邮箱</th>
                  <th className="px-4 py-3 text-left font-medium">邮箱密码</th>
                  <th className="px-4 py-3 text-left font-medium">网址</th>
                  <th className="px-4 py-3 text-left font-medium">入库时间</th>
                  <th className="px-4 py-3 text-left font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((account, index) => {
                  const isFirst =
                    sortKey === "inboundAt" &&
                    sortDir === "asc" &&
                    index === 0 &&
                    !filter;
                  return (
                    <tr
                      key={account.id}
                      className={cn(
                        "border-b border-border transition-colors hover:bg-muted/30",
                        selected.has(account.id) && "bg-primary/5",
                        isFirst && "bg-primary/[0.03]"
                      )}
                    >
                      <td className={cn("px-4", rowPadding)}>
                        <button
                          type="button"
                          onClick={() => toggleSelect(account.id)}
                        >
                          {selected.has(account.id) ? (
                            <CheckSquare className="h-4 w-4 text-primary" />
                          ) : (
                            <Square className="h-4 w-4 text-muted-foreground" />
                          )}
                        </button>
                      </td>
                      <td className={cn("px-4 font-mono", rowPadding)}>
                        <div className="flex items-center gap-2">
                          {isFirst && (
                            <Badge variant="fifo" className="text-[10px]">
                              FIFO 队首
                            </Badge>
                          )}
                          <button
                            type="button"
                            className="hover:text-primary"
                            onClick={() => copyAccount(account)}
                          >
                            {account.username}
                          </button>
                        </div>
                      </td>
                      <td className={cn("px-4", rowPadding)}>
                        <PasswordField value={account.password} />
                      </td>
                      <td className={cn("px-4", rowPadding)}>
                        {account.email ? (
                          <PasswordField value={account.email} />
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className={cn("px-4", rowPadding)}>
                        {account.emailPassword ? (
                          <PasswordField value={account.emailPassword} />
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className={cn("px-4 max-w-[140px] truncate", rowPadding)}>
                        {account.url ? (
                          <span className="text-xs text-blue-600">{account.url}</span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className={cn("px-4 text-xs text-muted-foreground whitespace-nowrap", rowPadding)}>
                        {formatDateTime(account.inboundAt)}
                      </td>
                      <td className={cn("px-4", rowPadding)}>
                        <div className="flex gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => copyAccount(account)}
                            aria-label="复制"
                          >
                            <Copy className="h-3.5 w-3.5" />
                          </Button>
                          <Button variant="ghost" size="sm" className="text-xs">
                            出库
                          </Button>
                        </div>
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
  );
}
