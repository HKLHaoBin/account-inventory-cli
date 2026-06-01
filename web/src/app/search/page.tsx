"use client";

import { useMemo, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Copy, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { PasswordField } from "@/components/ui/password-field";
import { writeAppClipboardText } from "@/lib/api";
import { mockHistory, mockInventory } from "@/lib/mock-data";
import { formatAccountLine, formatDateTime } from "@/lib/utils";
import type { SearchResult } from "@/types/account";
import { useState } from "react";

function searchAccounts(query: string): SearchResult[] {
  if (!query.trim()) return [];
  const q = query.toLowerCase();
  const results: SearchResult[] = [];

  for (const account of mockInventory) {
    const fields = [
      account.username,
      account.password,
      account.email,
      account.emailPassword,
      account.url,
    ].filter(Boolean) as string[];

    if (fields.some((f) => f.toLowerCase().includes(q))) {
      results.push({
        id: `inv-${account.id}`,
        source: "inventory",
        account,
        matchedField: account.username,
      });
    }
  }

  for (const record of mockHistory) {
    const fields = [
      record.username,
      record.password,
      record.email,
      record.emailPassword,
      record.url,
    ].filter(Boolean) as string[];

    if (fields.some((f) => f.toLowerCase().includes(q))) {
      results.push({
        id: `hist-${record.id}`,
        source: "history",
        account: record,
        matchedField: record.username,
      });
    }
  }

  return results;
}

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

  const results = useMemo(() => searchAccounts(query), [query]);
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

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">搜索结果</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {query ? (
            <>
              关键词「{query}」— 共 {results.length} 条结果
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

          {filtered.length === 0 ? (
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
                      onClick={() => copyResult(inventoryResults[0])}
                    >
                      <Upload className="h-4 w-4" />
                      出库此账号
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
