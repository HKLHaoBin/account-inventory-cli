"use client";

import { useEffect, useRef, useState } from "react";
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
import {
  outboundByUsername,
  searchAccounts,
} from "@/lib/api";
import { OutboundNoteField } from "@/components/notes/outbound-note-field";
import { OutboundCopyButton } from "@/components/outbound/outbound-copy-button";
import { useLastOutboundClipboard } from "@/hooks/use-last-outbound-clipboard";
import { shouldResetTopbarNoteDraft } from "@/components/notes/note-overwrite-logic";
import type { SearchResult } from "@/types/account";

interface TopBarProps {
  onQuickOutbound?: () => void;
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
  const topbarDraftKeyRef = useRef({ query: "", hitUsername: null as string | null });
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [outboundBusy, setOutboundBusy] = useState(false);
  const [outboundNote, setOutboundNote] = useState("");
  const [outboundOverwriteNote, setOutboundOverwriteNote] = useState(false);
  const [outboundSuccess, setOutboundSuccess] = useState(false);
  const [outboundCopyError, setOutboundCopyError] = useState("");
  const {
    clipboardText,
    remember,
    clear: clearClipboard,
    copy,
    copying,
    copied,
  } = useLastOutboundClipboard();

  useEffect(() => {
    const q = query.trim();
    if (!q) return;

    let ignore = false;
    const timer = window.setTimeout(() => {
      setLoading(true);
      setSearchError("");
      searchAccounts(q)
        .then((payload) => {
          if (ignore) return;
          setResults(payload);
        })
        .catch((error) => {
          if (ignore) return;
          setResults([]);
          setSearchError(
            error instanceof Error ? error.message : "搜索失败"
          );
        })
        .finally(() => {
          if (!ignore) setLoading(false);
        });
    }, 300);

    return () => {
      ignore = true;
      window.clearTimeout(timer);
    };
  }, [query]);

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
        setResults([]);
        setLoading(false);
        setSearchError("");
        clearOutboundNoteDraft();
        clearClipboard();
        setOutboundSuccess(false);
        setOutboundCopyError("");
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
  const uniqueHitUsername = uniqueInventoryHit
    ? inventoryResults[0]?.account.username ?? null
    : null;

  function clearOutboundNoteDraft() {
    setOutboundNote("");
    setOutboundOverwriteNote(false);
  }

  useEffect(() => {
    const prev = topbarDraftKeyRef.current;
    const next = { query, hitUsername: uniqueHitUsername };
    if (shouldResetTopbarNoteDraft(prev, next)) {
      clearOutboundNoteDraft();
    }
    topbarDraftKeyRef.current = next;
  }, [query, uniqueHitUsername]);

  function finishOutboundFlow() {
    setQuery("");
    setResults([]);
    setLoading(false);
    setSearchError("");
    clearOutboundNoteDraft();
    clearClipboard();
    setOutboundSuccess(false);
    setOutboundCopyError("");
    setOpen(false);
  }

  const handleUniqueOutbound = async () => {
    const hit = inventoryResults[0];
    if (!hit || outboundBusy) return;

    setOutboundBusy(true);
    setSearchError("");
    setOutboundCopyError("");
    try {
      const payload = await outboundByUsername(hit.account.username, {
        note: outboundNote.trim() || undefined,
        overwriteNote: outboundOverwriteNote,
      });
      const text = payload.clipboardText ?? "";
      remember(text);
      const copiedOk = text ? await copy(text) : true;
      const q = query.trim();
      if (q) {
        const updated = await searchAccounts(q);
        setResults(updated);
      } else {
        setResults([]);
      }
      clearOutboundNoteDraft();
      setOutboundSuccess(true);
      if (!copiedOk) {
        setOutboundCopyError("已出库，复制失败请点重新复制");
      }
    } catch (error) {
      setSearchError(
        error instanceof Error ? error.message : "出库失败"
      );
    } finally {
      setOutboundBusy(false);
    }
  };

  async function handleCopyOutbound() {
    setOutboundCopyError("");
    const ok = await copy();
    if (!ok && clipboardText) {
      setOutboundCopyError("复制到剪贴板失败，请重试");
    }
  }

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
            const value = e.target.value;
            setQuery(value);
            if (!value.trim()) {
              setResults([]);
              setLoading(false);
              setSearchError("");
              clearOutboundNoteDraft();
              clearClipboard();
              setOutboundSuccess(false);
              setOutboundCopyError("");
            } else {
              setResults([]);
              setLoading(true);
              setSearchError("");
            }
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
              setResults([]);
              setLoading(false);
              setSearchError("");
              clearOutboundNoteDraft();
              clearClipboard();
              setOutboundSuccess(false);
              setOutboundCopyError("");
              setOpen(false);
            }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        )}

        {open && query.trim() && (
          <div className="absolute left-0 right-0 top-full z-40 mt-2 overflow-hidden rounded-2xl border border-border bg-card shadow-[0_12px_40px_rgba(15,23,42,0.12)]">
            {loading ? (
              <p className="px-4 py-6 text-center text-sm text-muted-foreground">
                搜索中…
              </p>
            ) : searchError ? (
              <p className="px-4 py-6 text-center text-sm text-red-600">
                {searchError}
              </p>
            ) : results.length === 0 ? (
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
                        className="flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2.5 text-left text-sm hover:bg-muted transition-colors"
                        onClick={() => {
                          router.push(`/search?q=${encodeURIComponent(query)}`);
                          setOpen(false);
                        }}
                      >
                        <span className="min-w-0">
                          <span className="block truncate">
                            {highlightMatch(r.account.username, query)}
                          </span>
                          {r.account.note?.trim() && (
                            <span className="block truncate text-xs text-muted-foreground">
                              {r.account.note}
                            </span>
                          )}
                        </span>
                        <Badge variant="inventory" className="shrink-0">
                          库存
                        </Badge>
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
                        className="flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2.5 text-left text-sm hover:bg-muted transition-colors"
                        onClick={() => {
                          router.push(`/search?q=${encodeURIComponent(query)}`);
                          setOpen(false);
                        }}
                      >
                        <span className="min-w-0">
                          <span className="block truncate">
                            {highlightMatch(r.account.username, query)}
                          </span>
                          {r.account.note?.trim() && (
                            <span className="block truncate text-xs text-muted-foreground">
                              {r.account.note}
                            </span>
                          )}
                        </span>
                        <Badge variant="history" className="shrink-0">
                          历史
                        </Badge>
                      </button>
                    ))}
                  </div>
                )}
                {uniqueInventoryHit && !outboundSuccess && (
                  <div className="mt-2 space-y-2 border-t border-border p-2">
                    <OutboundNoteField
                      existingNote={inventoryResults[0].account.note}
                      value={outboundNote}
                      onChange={setOutboundNote}
                      overwriteNote={outboundOverwriteNote}
                      onOverwriteNoteChange={setOutboundOverwriteNote}
                      disabled={outboundBusy}
                    />
                    <Button
                      className="w-full"
                      size="sm"
                      onClick={handleUniqueOutbound}
                      disabled={outboundBusy}
                    >
                      {outboundBusy ? "出库中…" : "出库此账号并复制"}
                    </Button>
                  </div>
                )}
                {outboundSuccess && (
                  <div className="mt-2 space-y-2 border-t border-border bg-emerald-50 p-2 dark:bg-emerald-950/30">
                    <p className="text-center text-sm font-medium text-emerald-700 dark:text-emerald-300">
                      已出库
                    </p>
                    {outboundCopyError && (
                      <p className="text-center text-sm text-red-600">
                        {outboundCopyError}
                      </p>
                    )}
                    <div className="flex gap-2">
                      <OutboundCopyButton
                        className="flex-1"
                        size="sm"
                        clipboardText={clipboardText}
                        copying={copying}
                        copied={copied}
                        onCopy={handleCopyOutbound}
                      />
                      <Button
                        className="flex-1"
                        size="sm"
                        onClick={finishOutboundFlow}
                      >
                        完成
                      </Button>
                    </div>
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
