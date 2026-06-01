"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Search,
  HelpCircle,
  Zap,
  Boxes,
  X,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { writeAppClipboardText } from "@/lib/api";
import { formatAccountLine } from "@/lib/utils";
import { mockHistory, mockInventory } from "@/lib/mock-data";
import type { SearchResult } from "@/types/account";

interface TopBarProps {
  onQuickOutbound?: () => void;
}

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

    const matched = fields.find((f) => f.toLowerCase().includes(q));
    if (matched) {
      results.push({
        id: `inv-${account.id}`,
        source: "inventory",
        account,
        matchedField: matched,
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

    const matched = fields.find((f) => f.toLowerCase().includes(q));
    if (matched) {
      results.push({
        id: `hist-${record.id}`,
        source: "history",
        account: record,
        matchedField: matched,
      });
    }
  }

  return results;
}

function highlightMatch(text: string, query: string) {
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

export function TopBar({ onQuickOutbound }: TopBarProps) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<SearchResult[]>([]);

  const doSearch = useCallback((q: string) => {
    setResults(searchAccounts(q));
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => doSearch(query), 300);
    return () => clearTimeout(timer);
  }, [query, doSearch]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "/" && !e.ctrlKey && !e.metaKey) {
        const tag = (e.target as HTMLElement).tagName;
        if (tag === "INPUT" || tag === "TEXTAREA") return;
        e.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
      if (e.key === "Escape") {
        setQuery("");
        setOpen(false);
        inputRef.current?.blur();
      }
      if (e.key === "o" || e.key === "O") {
        const tag = (e.target as HTMLElement).tagName;
        if (tag === "INPUT" || tag === "TEXTAREA") return;
        onQuickOutbound?.();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onQuickOutbound]);

  const inventoryResults = results.filter((r) => r.source === "inventory");
  const historyResults = results.filter((r) => r.source === "history");
  const uniqueInventoryHit = inventoryResults.length === 1 && historyResults.length === 0;

  return (
    <header className="flex h-16 shrink-0 items-center gap-4 border-b border-border bg-card/80 px-6 backdrop-blur-sm">
      <div className="flex items-center gap-2 lg:hidden">
        <Boxes className="h-5 w-5 text-primary" />
        <span className="text-sm font-semibold">账号出入库</span>
      </div>

      <div className="relative mx-auto w-full max-w-xl flex-1">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder="全局搜索账号… 按 / 聚焦"
          className="pl-9 pr-9"
        />
        {query && (
          <button
            type="button"
            onClick={() => {
              setQuery("");
              setOpen(false);
            }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        )}

        {open && query && (
          <div className="absolute left-0 right-0 top-full z-40 mt-2 overflow-hidden rounded-2xl border border-border bg-card shadow-[0_12px_40px_rgba(15,23,42,0.12)]">
            {results.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-muted-foreground">
                未找到匹配结果
              </p>
            ) : (
              <div className="max-h-80 overflow-y-auto p-2">
                {inventoryResults.length > 0 && (
                  <div className="mb-2">
                    <p className="px-2 py-1 text-xs font-medium text-muted-foreground">
                      库存 ({inventoryResults.length})
                    </p>
                    {inventoryResults.map((r) => (
                      <button
                        key={r.id}
                        type="button"
                        className="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm hover:bg-muted transition-colors"
                        onClick={() => {
                          router.push(`/search?q=${encodeURIComponent(query)}`);
                          setOpen(false);
                        }}
                      >
                        <span>{highlightMatch(r.account.username, query)}</span>
                        <Badge variant="inventory">库存</Badge>
                      </button>
                    ))}
                  </div>
                )}
                {historyResults.length > 0 && (
                  <div>
                    <p className="px-2 py-1 text-xs font-medium text-muted-foreground">
                      出库历史 ({historyResults.length})
                    </p>
                    {historyResults.map((r) => (
                      <button
                        key={r.id}
                        type="button"
                        className="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm hover:bg-muted transition-colors"
                        onClick={() => {
                          router.push(`/search?q=${encodeURIComponent(query)}`);
                          setOpen(false);
                        }}
                      >
                        <span>{highlightMatch(r.account.username, query)}</span>
                        <Badge variant="history">历史</Badge>
                      </button>
                    ))}
                  </div>
                )}
                {uniqueInventoryHit && (
                  <div className="mt-2 border-t border-border p-2">
                    <Button
                      className="w-full"
                      size="sm"
                      onClick={() => {
                        const a = inventoryResults[0].account;
                        void writeAppClipboardText(
                          formatAccountLine(
                            a.username,
                            a.password,
                            a.email,
                            a.emailPassword,
                            a.url
                          )
                        );
                        setOpen(false);
                      }}
                    >
                      出库此账号并复制
                    </Button>
                  </div>
                )}
                <button
                  type="button"
                  className="mt-1 w-full rounded-xl px-3 py-2 text-center text-xs text-primary hover:bg-primary/5"
                  onClick={() => {
                    router.push(`/search?q=${encodeURIComponent(query)}`);
                    setOpen(false);
                  }}
                >
                  查看全部结果 →
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          onClick={onQuickOutbound}
          className="hidden sm:inline-flex"
        >
          <Zap className="h-4 w-4" />
          快捷出库
        </Button>
        <Link href="/settings">
          <Button variant="ghost" size="icon" aria-label="帮助">
            <HelpCircle className="h-4 w-4" />
          </Button>
        </Link>
      </div>
    </header>
  );
}
