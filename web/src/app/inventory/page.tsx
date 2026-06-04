"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowUpDown,
  Copy,
  CheckSquare,
  Square,
  PackageOpen,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { PasswordField } from "@/components/ui/password-field";
import { Pagination } from "@/components/ui/pagination";
import { OutboundCopyButton } from "@/components/outbound/outbound-copy-button";
import { useLastOutboundClipboard } from "@/hooks/use-last-outbound-clipboard";
import {
  DEFAULT_PAGE_SIZE,
  fetchInventory,
  outboundByUsername,
  writeAppClipboardText,
} from "@/lib/api";
import { subscribeDatabaseChanged } from "@/lib/database-events";
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
  const [page, setPage] = useState(1);
  const [pageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [density, setDensity] = useState<"comfortable" | "compact">(
    "comfortable"
  );
  const [records, setRecords] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [outboundUsername, setOutboundUsername] = useState<string | null>(null);
  const [outboundRowErrors, setOutboundRowErrors] = useState<
    Record<string, string>
  >({});
  const [lastOutboundCopyFailed, setLastOutboundCopyFailed] = useState(false);
  const {
    clipboardText,
    remember,
    clear,
    copy,
    copying,
    copied,
  } = useLastOutboundClipboard();

  const showFifoBadge =
    page === 1 &&
    sortKey === "inboundAt" &&
    sortDir === "asc" &&
    !filter.trim();

  const loadInventory = useCallback(
    async (ignoreResult?: () => boolean) => {
      setLoading(true);
      setError("");
      try {
        const payload = await fetchInventory({
          page,
          pageSize,
          q: filter.trim() || undefined,
          sortBy: sortKey,
          sortDir,
        });
        if (ignoreResult?.()) return;
        if (payload.records.length === 0 && page > 1) {
          setPage((current) => Math.max(1, current - 1));
          return;
        }
        setRecords(payload.records);
        setTotal(payload.total);
        setTotalPages(payload.totalPages);
      } catch (requestError) {
        if (ignoreResult?.()) return;
        setError(
          requestError instanceof Error ? requestError.message : "库存读取失败"
        );
        setRecords([]);
        setTotal(0);
        setTotalPages(1);
        setSelected(new Set());
      } finally {
        if (!ignoreResult?.()) setLoading(false);
      }
    },
    [filter, page, pageSize, sortDir, sortKey]
  );

  useEffect(() => {
    let ignore = false;
    const timer = window.setTimeout(() => {
      void loadInventory(() => ignore);
    }, 0);
    return () => {
      ignore = true;
      window.clearTimeout(timer);
    };
  }, [loadInventory]);

  useEffect(() => {
    setSelected(new Set());
  }, [page, filter, sortKey, sortDir]);

  useEffect(
    () =>
      subscribeDatabaseChanged(() => {
        clear();
        setLastOutboundCopyFailed(false);
        setOutboundRowErrors({});
        setOutboundUsername(null);
        setSelected(new Set());
        setPage(1);
        void loadInventory();
      }),
    [loadInventory, clear]
  );

  const visibleSelectedCount = useMemo(
    () => records.filter((a) => selected.has(a.id)).length,
    [selected, records]
  );

  const toggleSort = (key: SortKey) => {
    setPage(1);
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
    const visibleIds = new Set(records.map((a) => a.id));
    setSelected((prev) => {
      const allVisibleSelected =
        visibleIds.size > 0 && [...visibleIds].every((id) => prev.has(id));
      const next = new Set(prev);
      if (allVisibleSelected) {
        for (const id of visibleIds) next.delete(id);
      } else {
        for (const id of visibleIds) next.add(id);
      }
      return next;
    });
  };

  const copyAccount = (a: Account) => {
    void writeAppClipboardText(
      formatAccountLine(
        a.username,
        a.password,
        a.email,
        a.emailPassword,
        a.url
      )
    );
  };

  const outboundAccount = async (account: Account) => {
    if (outboundUsername) return;
    setOutboundUsername(account.username);
    setOutboundRowErrors((current) => {
      const next = { ...current };
      delete next[account.id];
      return next;
    });
    setLastOutboundCopyFailed(false);
    try {
      const payload = await outboundByUsername(account.username);
      const text = payload.clipboardText ?? "";
      remember(text);
      const copiedOk = text ? await copy(text) : true;
      setLastOutboundCopyFailed(!copiedOk);
      await loadInventory();
    } catch (requestError) {
      setOutboundRowErrors((current) => ({
        ...current,
        [account.id]:
          requestError instanceof Error ? requestError.message : "出库失败",
      }));
    } finally {
      setOutboundUsername(null);
    }
  };

  async function handleCopyOutbound() {
    setLastOutboundCopyFailed(false);
    const ok = await copy();
    if (!ok && clipboardText) {
      setLastOutboundCopyFailed(true);
    }
  }

  const rowPadding = density === "compact" ? "py-2" : "py-3.5";

  if (loading && records.length === 0 && total === 0) {
    return (
      <div className="space-y-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">库存列表</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            正在加载库存...
          </p>
        </div>
        <Card>
          <CardContent className="py-8 text-sm text-muted-foreground">
            正在加载库存...
          </CardContent>
        </Card>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">库存列表</h1>
          <p className="mt-1 text-sm text-red-600">库存读取失败：{error}</p>
        </div>
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-6">
            <p className="text-sm text-muted-foreground">
              当前未展示任何预设数据。
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void loadInventory()}
            >
              重试
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (total === 0 && !filter.trim()) {
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
            共 {total} 条 · 默认按 FIFO 入库时间排序
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="搜索库存"
          value={filter}
          onChange={(e) => {
            setPage(1);
            setFilter(e.target.value);
          }}
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
          disabled={visibleSelectedCount === 0}
          onClick={() => {
            const lines = records
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
            void writeAppClipboardText(lines);
          }}
        >
          <Copy className="h-4 w-4" />
          复制选中 ({visibleSelectedCount})
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

      {clipboardText && (
        <Card className="border-emerald-200 bg-emerald-50 dark:bg-emerald-950/30">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-3">
            <p className="text-sm font-medium text-emerald-700 dark:text-emerald-300">
              {lastOutboundCopyFailed
                ? "已出库，复制失败可点重新复制"
                : "账号已出库，可重新复制"}
            </p>
            <OutboundCopyButton
              size="sm"
              clipboardText={clipboardText}
              copying={copying}
              copied={copied}
              onCopy={handleCopyOutbound}
            />
          </CardContent>
        </Card>
      )}

      {records.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-sm text-muted-foreground">
            没有匹配的库存记录
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/40">
                    <th className="px-2 py-3 text-left font-medium whitespace-nowrap">
                      操作
                    </th>
                    <th className="w-10 px-4 py-3">
                      <button type="button" onClick={toggleAll}>
                        {visibleSelectedCount === records.length &&
                        records.length > 0 ? (
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
                    <th className="px-4 py-3 text-left font-medium">备注</th>
                    <th className="px-4 py-3 text-left font-medium">入库时间</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((account, index) => {
                    const isFirst = showFifoBadge && index === 0;
                    const rowError = outboundRowErrors[account.id];
                    return (
                      <tr
                        key={account.id}
                        className={cn(
                          "border-b border-border transition-colors hover:bg-muted/30",
                          selected.has(account.id) && "bg-primary/5",
                          isFirst && "bg-primary/[0.03]"
                        )}
                      >
                        <td className={cn("px-2", rowPadding)}>
                          <div className="flex flex-col gap-1">
                            <div className="flex items-center gap-1 whitespace-nowrap">
                              <Button
                                variant="secondary"
                                size="sm"
                                className="h-8 px-2 text-xs"
                                disabled={Boolean(outboundUsername)}
                                onClick={() => void outboundAccount(account)}
                              >
                                <Upload className="h-3.5 w-3.5" />
                                {outboundUsername === account.username
                                  ? "出库中…"
                                  : "出库"}
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8 shrink-0"
                                onClick={() => copyAccount(account)}
                                aria-label="复制"
                              >
                                <Copy className="h-3.5 w-3.5" />
                              </Button>
                            </div>
                            {rowError && (
                              <p className="max-w-[140px] text-xs text-red-600">
                                {rowError}
                              </p>
                            )}
                          </div>
                        </td>
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
                        <td
                          className={cn(
                            "px-4 max-w-[140px] truncate",
                            rowPadding
                          )}
                        >
                          {account.url ? (
                            <span className="text-xs text-blue-600">
                              {account.url}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td
                          className={cn(
                            "px-4 break-words whitespace-pre-wrap text-xs text-muted-foreground",
                            rowPadding
                          )}
                        >
                          {account.note?.trim() ? account.note : "—"}
                        </td>
                        <td
                          className={cn(
                            "px-4 text-xs text-muted-foreground whitespace-nowrap",
                            rowPadding
                          )}
                        >
                          {formatDateTime(account.inboundAt)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="space-y-2 p-3 md:hidden">
              <div className="flex items-center gap-2 border-b border-border pb-2">
                <button type="button" onClick={toggleAll}>
                  {visibleSelectedCount === records.length && records.length > 0 ? (
                    <CheckSquare className="h-4 w-4 text-primary" />
                  ) : (
                    <Square className="h-4 w-4 text-muted-foreground" />
                  )}
                </button>
                <span className="text-xs text-muted-foreground">
                  全选 ({visibleSelectedCount}/{records.length})
                </span>
              </div>
              {records.map((account, index) => {
                const isFirst = showFifoBadge && index === 0;
                const rowError = outboundRowErrors[account.id];
                return (
                  <div
                    key={`${account.id}-mobile`}
                    className={cn(
                      "rounded-xl border border-border p-3",
                      selected.has(account.id) && "bg-primary/5",
                      isFirst && "bg-primary/[0.03]"
                    )}
                  >
                    <div className="flex items-start gap-2">
                      <div className="flex shrink-0 flex-col gap-1">
                        <div className="flex items-center gap-1">
                          <Button
                            variant="secondary"
                            size="sm"
                            className="h-8 px-2 text-xs"
                            disabled={Boolean(outboundUsername)}
                            onClick={() => void outboundAccount(account)}
                          >
                            <Upload className="h-3.5 w-3.5" />
                            {outboundUsername === account.username
                              ? "出库中…"
                              : "出库"}
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 shrink-0"
                            onClick={() => copyAccount(account)}
                            aria-label="复制"
                          >
                            <Copy className="h-4 w-4" />
                          </Button>
                        </div>
                        {rowError && (
                          <p className="max-w-[140px] text-xs text-red-600">
                            {rowError}
                          </p>
                        )}
                      </div>
                      <button
                        type="button"
                        className="pt-0.5"
                        onClick={() => toggleSelect(account.id)}
                      >
                        {selected.has(account.id) ? (
                          <CheckSquare className="h-5 w-5 text-primary" />
                        ) : (
                          <Square className="h-5 w-5 text-muted-foreground" />
                        )}
                      </button>
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          {isFirst && (
                            <Badge variant="fifo" className="text-[10px]">
                              FIFO 队首
                            </Badge>
                          )}
                          <span className="font-mono text-sm font-medium">
                            {account.username}
                          </span>
                        </div>
                        <PasswordField value={account.password} />
                        {account.email && (
                          <PasswordField value={account.email} />
                        )}
                        {account.emailPassword && (
                          <PasswordField value={account.emailPassword} />
                        )}
                        {account.url && (
                          <p className="break-all text-xs text-blue-600">
                            {account.url}
                          </p>
                        )}
                        {account.note?.trim() && (
                          <p className="break-words whitespace-pre-wrap text-xs text-muted-foreground">
                            备注：{account.note}
                          </p>
                        )}
                        <p className="text-xs text-muted-foreground">
                          入库 {formatDateTime(account.inboundAt)}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      <Pagination
        total={total}
        page={page}
        pageSize={pageSize}
        totalPages={totalPages}
        onPageChange={setPage}
        disabled={loading}
      />
    </div>
  );
}
