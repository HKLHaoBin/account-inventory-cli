"use client";

import { useCallback, useEffect, Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Copy, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { PasswordField } from "@/components/ui/password-field";
import {
  outboundByUsername,
  searchAccounts,
  writeAppClipboardText,
  writeOutboundClipboardText,
} from "@/lib/api";
import { subscribeDatabaseChanged } from "@/lib/database-events";
import { formatAccountLine, formatDateTime } from "@/lib/utils";
import type { SearchResult } from "@/types/account";

function highlight(text: string, query: string) {
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="rounded bg-primary/20 px-0.5 text-primary">
        {text.slice(idx, idx + query.length)}
      </mark>
      {text.slice(idx + query.length)}
    </>
  );
}

function SearchContent() {
  const searchParams = useSearchParams();
  const query = searchParams.get("q") || "";
  const [tab, setTab] = useState<"all" | "inventory" | "history">("all");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [outboundUsername, setOutboundUsername] = useState("");

  const inventoryResults = results.filter((r) => r.source === "inventory");
  const historyResults = results.filter((r) => r.source === "history");
  const uniqueInventoryHit =
    inventoryResults.length === 1 && historyResults.length === 0;

  const filtered =
    tab === "all"
      ? results
      : tab === "inventory"
        ? inventoryResults
        : historyResults;

  const loadResults = useCallback(
    async (ignoreResult?: () => boolean) => {
      const q = query.trim();
      if (!q) {
        setResults([]);
        setError("");
        setLoading(false);
        return;
      }

      setLoading(true);
      setError("");
      try {
        const payload = await searchAccounts(q);
        if (ignoreResult?.()) return;
        setResults(payload);
      } catch (requestError) {
        if (ignoreResult?.()) return;
        setResults([]);
        setError(
          requestError instanceof Error ? requestError.message : "搜索失败"
        );
      } finally {
        if (!ignoreResult?.()) setLoading(false);
      }
    },
    [query]
  );

  useEffect(() => {
    let ignore = false;
    const timer = window.setTimeout(() => {
      void loadResults(() => ignore);
    }, 0);
    return () => {
      ignore = true;
      window.clearTimeout(timer);
    };
  }, [loadResults]);

  useEffect(
    () => subscribeDatabaseChanged(() => void loadResults()),
    [loadResults]
  );

  const copyResult = (r: SearchResult) => {
    const a = r.account;
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

  const outboundResult = async (r: SearchResult) => {
    if (r.source !== "inventory" || outboundUsername) return;
    setOutboundUsername(r.account.username);
    setError("");
    try {
      const payload = await outboundByUsername(r.account.username);
      if (payload.clipboardText) {
        await writeOutboundClipboardText(payload.clipboardText);
      }
      await loadResults();
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "出库失败"
      );
    } finally {
      setOutboundUsername("");
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">搜索结果</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {query ? (
            <>
              关键词「{query}」- 共 {results.length} 条结果
            </>
          ) : (
            "请在顶部搜索框输入关键词"
          )}
        </p>
      </div>

      {query && (
        <>
          <div className="flex gap-2">
            {(
              [
                ["all", `全部 (${results.length})`],
                ["inventory", `库存 (${inventoryResults.length})`],
                ["history", `历史 (${historyResults.length})`],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setTab(key)}
                className={`rounded-[10px] px-4 py-2 text-sm font-medium transition-all ${
                  tab === key
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "bg-muted text-muted-foreground hover:bg-muted/80"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {error && (
            <Card className="border-red-200 bg-red-50">
              <CardContent className="py-3 text-sm text-red-700">
                {error}
              </CardContent>
            </Card>
          )}

          {loading ? (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                搜索中…
              </CardContent>
            </Card>
          ) : filtered.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                未找到匹配结果
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {filtered.map((r) => (
                <Card key={r.id}>
                  <CardContent className="flex flex-wrap items-center justify-between gap-4 p-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-medium">
                          {highlight(r.account.username, query)}
                        </span>
                        <Badge
                          variant={
                            r.source === "inventory" ? "inventory" : "history"
                          }
                        >
                          {r.source === "inventory" ? "库存" : "历史"}
                        </Badge>
                      </div>
                      <PasswordField value={r.account.password} />
                      {"outboundAt" in r.account && r.account.outboundAt && (
                        <p className="text-xs text-muted-foreground">
                          出库：{formatDateTime(r.account.outboundAt)}
                        </p>
                      )}
                      {"inboundAt" in r.account && r.source === "inventory" && (
                        <p className="text-xs text-muted-foreground">
                          入库：{formatDateTime(r.account.inboundAt)}
                        </p>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => copyResult(r)}
                      >
                        <Copy className="h-4 w-4" />
                        复制
                      </Button>
                      {r.source === "inventory" && (
                        <Button
                          size="sm"
                          onClick={() => void outboundResult(r)}
                          disabled={Boolean(outboundUsername)}
                        >
                          <Upload className="h-4 w-4" />
                          {outboundUsername === r.account.username
                            ? "出库中…"
                            : "出库"}
                        </Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}

              {uniqueInventoryHit && tab !== "history" && (
                <Card className="border-primary/30 bg-primary/5">
                  <CardContent className="flex items-center justify-between p-4">
                    <div>
                      <p className="font-medium">唯一库存命中</p>
                      <p className="text-sm text-muted-foreground">
                        可直接出库此账号（非 FIFO）
                      </p>
                    </div>
                    <Button
                      onClick={() => void outboundResult(inventoryResults[0])}
                      disabled={Boolean(outboundUsername)}
                    >
                      <Upload className="h-4 w-4" />
                      {outboundUsername ? "出库中…" : "出库此账号"}
                    </Button>
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="p-6 text-muted-foreground">加载中…</div>}>
      <SearchContent />
    </Suspense>
  );
}
