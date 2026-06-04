"use client";

import { useCallback, useEffect, useRef, Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Copy, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { PasswordField } from "@/components/ui/password-field";
import { Pagination } from "@/components/ui/pagination";
import { OutboundNoteField } from "@/components/notes/outbound-note-field";
import { OutboundCopyButton } from "@/components/outbound/outbound-copy-button";
import { useLastOutboundClipboard } from "@/hooks/use-last-outbound-clipboard";
import {
  DEFAULT_PAGE_SIZE,
  outboundByUsername,
  searchAccounts,
  writeAppClipboardText,
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
  const [page, setPage] = useState(1);
  const [pageSize] = useState(DEFAULT_PAGE_SIZE);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [inventoryTotal, setInventoryTotal] = useState(0);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [outboundUsername, setOutboundUsername] = useState("");
  const [outboundNotes, setOutboundNotes] = useState<
    Record<string, { note: string; overwriteNote: boolean }>
  >({});
  const {
    clipboardText,
    remember,
    copy,
    copying,
    copied,
  } = useLastOutboundClipboard();
  const [copyError, setCopyError] = useState("");
  const [reloadToken, setReloadToken] = useState(0);
  const lastQueryRef = useRef(query);

  const allTotal = inventoryTotal + historyTotal;
  const inventoryResults = results.filter((r) => r.source === "inventory");
  const historyResults = results.filter((r) => r.source === "history");
  const uniqueInventoryHit =
    tab === "all" &&
    inventoryTotal === 1 &&
    historyTotal === 0 &&
    inventoryResults.length === 1 &&
    historyResults.length === 0;

  const loadResults = useCallback(
    async (ignoreResult?: () => boolean) => {
      const q = query.trim();
      if (lastQueryRef.current !== query) {
        lastQueryRef.current = query;
        if (page !== 1) {
          setPage(1);
          return;
        }
      }
      if (!q) {
        setResults([]);
        setTotal(0);
        setTotalPages(1);
        setInventoryTotal(0);
        setHistoryTotal(0);
        setError("");
        setLoading(false);
        return;
      }

      setLoading(true);
      setError("");
      try {
        const payload = await searchAccounts(q, {
          page,
          pageSize,
          source: tab,
        });
        if (ignoreResult?.()) return;
        if (payload.results.length === 0 && page > 1) {
          setPage((current) => Math.max(1, current - 1));
          return;
        }
        setResults(payload.results);
        setTotal(payload.total);
        setTotalPages(payload.totalPages);
        setInventoryTotal(payload.inventoryTotal);
        setHistoryTotal(payload.historyTotal);
      } catch (requestError) {
        if (ignoreResult?.()) return;
        setResults([]);
        setTotal(0);
        setTotalPages(1);
        setInventoryTotal(0);
        setHistoryTotal(0);
        setError(
          requestError instanceof Error ? requestError.message : "搜索失败"
        );
      } finally {
        if (!ignoreResult?.()) setLoading(false);
      }
    },
    [query, page, pageSize, tab]
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
  }, [loadResults, reloadToken]);

  useEffect(
    () =>
      subscribeDatabaseChanged(() => {
        setPage(1);
        setReloadToken((value) => value + 1);
      }),
    []
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
    const username = r.account.username;
    const draft = outboundNotes[username] ?? { note: "", overwriteNote: false };
    setOutboundUsername(username);
    setError("");
    setCopyError("");
    try {
      const payload = await outboundByUsername(username, {
        note: draft.note.trim() || undefined,
        overwriteNote: draft.overwriteNote,
      });
      const text = payload.clipboardText ?? "";
      remember(text);
      const copiedOk = text ? await copy(text) : true;
      if (!copiedOk) {
        setCopyError("已出库，复制失败请点重新复制");
      }
      setOutboundNotes((current) => {
        const next = { ...current };
        delete next[username];
        return next;
      });
      await loadResults();
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "出库失败"
      );
    } finally {
      setOutboundUsername("");
    }
  };

  async function handleCopyOutbound() {
    setCopyError("");
    const ok = await copy();
    if (!ok && clipboardText) {
      setCopyError("复制到剪贴板失败，请重试");
    }
  }

  function updateOutboundNote(
    username: string,
    patch: Partial<{ note: string; overwriteNote: boolean }>
  ) {
    setOutboundNotes((current) => ({
      ...current,
      [username]: {
        note: patch.note ?? current[username]?.note ?? "",
        overwriteNote: patch.overwriteNote ?? current[username]?.overwriteNote ?? false,
      },
    }));
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">搜索结果</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {query ? (
            <>
              关键词「{query}」- 共 {allTotal} 条结果
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
                ["all", `全部 (${allTotal})`],
                ["inventory", `库存 (${inventoryTotal})`],
                ["history", `历史 (${historyTotal})`],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setTab(key);
                  setPage(1);
                }}
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

          {clipboardText && (
            <Card className="border-emerald-200 bg-emerald-50 dark:bg-emerald-950/30">
              <CardContent className="flex flex-wrap items-center justify-between gap-3 py-3">
                <p className="text-sm font-medium text-emerald-700 dark:text-emerald-300">
                  账号已出库，复制失败可点重新复制
                </p>
                <div className="flex items-center gap-2">
                  {copyError && (
                    <span className="text-sm text-red-600">{copyError}</span>
                  )}
                  <OutboundCopyButton
                    size="sm"
                    clipboardText={clipboardText}
                    copying={copying}
                    copied={copied}
                    onCopy={handleCopyOutbound}
                  />
                </div>
              </CardContent>
            </Card>
          )}

          {loading ? (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                搜索中…
              </CardContent>
            </Card>
          ) : results.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                未找到匹配结果
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {results.map((r) => (
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
                      {r.source === "inventory" && (
                        <p className="text-xs text-muted-foreground">
                          入库：{formatDateTime(r.account.inboundAt)}
                        </p>
                      )}
                      {r.account.note?.trim() && (
                        <p className="break-words whitespace-pre-wrap text-xs text-muted-foreground">
                          备注：{highlight(r.account.note, query)}
                        </p>
                      )}
                      {r.matchedField &&
                        r.account.note &&
                        r.matchedField === r.account.note && (
                          <p className="text-xs text-primary">
                            命中字段：备注
                          </p>
                        )}
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      {r.source === "inventory" && (
                        <OutboundNoteField
                          existingNote={r.account.note}
                          value={outboundNotes[r.account.username]?.note ?? ""}
                          onChange={(note) =>
                            updateOutboundNote(r.account.username, { note })
                          }
                          overwriteNote={
                            outboundNotes[r.account.username]?.overwriteNote ?? false
                          }
                          onOverwriteNoteChange={(overwriteNote) =>
                            updateOutboundNote(r.account.username, { overwriteNote })
                          }
                          disabled={Boolean(outboundUsername)}
                        />
                      )}
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
                              : "出库并复制"}
                          </Button>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}

              {uniqueInventoryHit && (
                <Card className="border-primary/30 bg-primary/5">
                  <CardContent className="flex flex-wrap items-center justify-between gap-4 p-4">
                    <div>
                      <p className="font-medium">唯一库存命中</p>
                      <p className="text-sm text-muted-foreground">
                        可直接出库此账号并复制（非 FIFO）
                      </p>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      <OutboundNoteField
                        existingNote={inventoryResults[0].account.note}
                        value={
                          outboundNotes[inventoryResults[0].account.username]?.note ?? ""
                        }
                        onChange={(note) =>
                          updateOutboundNote(inventoryResults[0].account.username, {
                            note,
                          })
                        }
                        overwriteNote={
                          outboundNotes[inventoryResults[0].account.username]
                            ?.overwriteNote ?? false
                        }
                        onOverwriteNoteChange={(overwriteNote) =>
                          updateOutboundNote(inventoryResults[0].account.username, {
                            overwriteNote,
                          })
                        }
                        disabled={Boolean(outboundUsername)}
                      />
                      <Button
                        onClick={() => void outboundResult(inventoryResults[0])}
                        disabled={Boolean(outboundUsername)}
                      >
                        <Upload className="h-4 w-4" />
                        {outboundUsername ? "出库中…" : "出库此账号并复制"}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          <Pagination
            total={total}
            page={page}
            pageSize={pageSize}
            totalPages={totalPages}
            onPageChange={setPage}
            disabled={loading}
          />
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
