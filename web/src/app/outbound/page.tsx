"use client";

import { useEffect, useMemo, useState } from "react";
import { Minus, Plus, Package, Download, Upload } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { PasswordField } from "@/components/ui/password-field";
import { BatchNoteControls } from "@/components/notes/batch-note-controls";
import { OutboundNoteField } from "@/components/notes/outbound-note-field";
import { OutboundCopyButton } from "@/components/outbound/outbound-copy-button";
import { useLastOutboundClipboard } from "@/hooks/use-last-outbound-clipboard";
import { commitFifo, previewFifo } from "@/lib/api";
import { subscribeDatabaseChanged } from "@/lib/database-events";
import { downloadTextFile } from "@/lib/download";
import { formatDateTime } from "@/lib/utils";
import type { FifoNoteEntry } from "@/types/account";

export default function OutboundPage() {
  const [quantity, setQuantity] = useState(1);
  const [fifoPreview, setFifoPreview] = useState({
    max: 0,
    quantity: 0,
    rows: [] as Awaited<ReturnType<typeof previewFifo>>["rows"],
  });
  const [fifoNotes, setFifoNotes] = useState<FifoNoteEntry[]>([]);
  const [fifoBusy, setFifoBusy] = useState(false);
  const [resultMessage, setResultMessage] = useState("");
  const {
    clipboardText,
    remember,
    clear: clearClipboard,
    copy,
    copying,
    copied,
  } = useLastOutboundClipboard();
  const [resultOpen, setResultOpen] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [reloadToken, setReloadToken] = useState(0);

  const max = fifoPreview.max;
  const clamped = Math.min(Math.max(quantity, 0), max);
  const preview = fifoPreview.rows;
  const chips = useMemo(
    () => Array.from(new Set([1, 5, 10, max].filter((n) => n > 0))),
    [max]
  );

  const fifoNotesByUsername = useMemo(
    () =>
      Object.fromEntries(
        fifoNotes.map((entry) => [
          entry.username,
          {
            note: entry.note ?? "",
            overwriteNote: entry.overwriteNote ?? false,
          },
        ])
      ),
    [fifoNotes]
  );

  useEffect(() => {
    let ignore = false;
    async function loadPreview() {
      try {
        const payload = await previewFifo(quantity);
        if (ignore) return;
        setFifoPreview(payload);
        setFifoNotes((current) => {
          const byUsername = new Map(
            current.map((entry) => [entry.username, entry])
          );
          return payload.rows.map((row) => {
            const existing = byUsername.get(row.username);
            return {
              username: row.username,
              note: existing?.note ?? row.note ?? "",
              overwriteNote: existing?.overwriteNote ?? false,
            };
          });
        });
        setLoadError("");
      } catch (error) {
        if (ignore) return;
        setLoadError(error instanceof Error ? error.message : "FIFO 预览失败");
      }
    }
    void loadPreview();
    return () => {
      ignore = true;
    };
  }, [quantity, reloadToken]);

  useEffect(
    () => subscribeDatabaseChanged(() => setReloadToken((token) => token + 1)),
    []
  );

  useEffect(() => {
    clearClipboard();
  }, [quantity, clearClipboard]);

  function updateFifoNote(
    username: string,
    patch: Partial<{ note: string; overwriteNote: boolean }>
  ) {
    setFifoNotes((entries) =>
      entries.map((entry) =>
        entry.username === username
          ? {
              ...entry,
              ...(patch.note !== undefined
                ? { note: patch.note, overwriteNote: false }
                : {}),
              ...(patch.overwriteNote !== undefined
                ? { overwriteNote: patch.overwriteNote }
                : {}),
            }
          : entry
      )
    );
  }

  async function handleCommit() {
    if (clamped === 0 || fifoBusy) return;
    setFifoBusy(true);
    setLoadError("");
    try {
      const payload = await commitFifo(quantity, fifoNotes);
      const text = payload.clipboardText ?? "";
      remember(text);
      const copiedOk = text ? await copy(text) : true;
      setResultMessage(
        copiedOk
          ? `已出库 ${payload.quantity} 条并复制到剪贴板`
          : `已出库 ${payload.quantity} 条，复制失败请点重新复制`
      );
      setResultOpen(true);
      setQuantity(1);
      setReloadToken((token) => token + 1);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "FIFO 出库失败");
    } finally {
      setFifoBusy(false);
    }
  }

  async function handleDownload() {
    if (clamped === 0 || fifoBusy) return;
    setFifoBusy(true);
    setLoadError("");
    try {
      const payload = await commitFifo(quantity, fifoNotes);
      remember(payload.clipboardText ?? "");
      if (payload.clipboardText) {
        downloadTextFile(payload.clipboardText);
      }
      setResultMessage(`已出库 ${payload.quantity} 条并下载 TXT`);
      setResultOpen(true);
      setQuantity(1);
      setReloadToken((token) => token + 1);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "FIFO 出库失败");
    } finally {
      setFifoBusy(false);
    }
  }

  async function handleCopy() {
    setLoadError("");
    const ok = await copy();
    if (!ok && clipboardText) {
      setLoadError("复制到剪贴板失败，请重试");
    }
  }

  if (max === 0 && !loadError) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <Package className="h-12 w-12 text-muted-foreground" />
        <p className="mt-4 text-lg font-medium">暂无库存</p>
        <Link href="/inbound">
          <Button className="mt-4">去入库</Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="text-center">
        <h1 className="text-2xl font-bold tracking-tight">FIFO 出库</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          按入库时间先进先出，出库并复制到剪贴板，失败可重新复制
        </p>
        <Badge variant="default" className="mt-3">
          当前库存 {max} 条
        </Badge>
        {loadError && (
          <p className="mt-2 text-sm text-red-600">{loadError}</p>
        )}
      </div>

      <Card>
        <CardHeader className="text-center">
          <CardTitle className="text-base">选择出库数量</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex items-center justify-center gap-4">
            <Button
              variant="outline"
              size="icon"
              className="h-12 w-12 rounded-xl"
              onClick={() => setQuantity((q) => Math.max(0, q - 1))}
              disabled={clamped <= 0}
            >
              <Minus className="h-5 w-5" />
            </Button>
            <input
              type="number"
              value={quantity}
              onChange={(e) => setQuantity(Number(e.target.value))}
              className="w-24 rounded-xl border-2 border-border bg-background px-3 py-3 text-center text-3xl font-bold focus:outline-none focus:ring-2 focus:ring-primary/30"
              min={0}
            />
            <Button
              variant="outline"
              size="icon"
              className="h-12 w-12 rounded-xl"
              onClick={() => setQuantity((q) => Math.min(max, q + 1))}
              disabled={clamped >= max}
            >
              <Plus className="h-5 w-5" />
            </Button>
          </div>

          <div className="flex flex-wrap justify-center gap-2">
            {chips.map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => setQuantity(n)}
                className={`rounded-[10px] px-4 py-2 text-sm font-medium transition-all ${
                  clamped === n
                    ? "bg-primary text-primary-foreground shadow-[0_2px_8px_rgba(30,64,175,0.25)]"
                    : "bg-muted text-muted-foreground hover:bg-muted/80"
                }`}
              >
                {n === max ? "全部" : n}
              </button>
            ))}
          </div>

          {quantity > max && (
            <p className="text-center text-sm text-amber-600">
              请求 {quantity}，实际出库 {max}
            </p>
          )}

          <BatchNoteControls
            rows={fifoNotes.map((entry) => ({
              clientId: entry.username,
              username: entry.username,
              note: entry.note,
              overwriteNote: entry.overwriteNote,
            }))}
            onRowsChange={(rows) =>
              setFifoNotes(
                rows.map((row) => ({
                  username: row.username ?? "",
                  note: row.note,
                  overwriteNote: row.overwriteNote,
                }))
              )
            }
            disabled={fifoBusy}
          />

          <div className="grid gap-2 sm:grid-cols-3">
            <Button
              className="w-full"
              size="lg"
              onClick={() => void handleCommit()}
              disabled={clamped === 0 || fifoBusy}
            >
              <Upload className="h-4 w-4" />
              出库并复制
            </Button>
            <OutboundCopyButton
              className="w-full"
              size="lg"
              clipboardText={clipboardText}
              copying={copying}
              copied={copied}
              onCopy={handleCopy}
              disabled={fifoBusy}
            />
            <Button
              className="w-full"
              variant="secondary"
              size="lg"
              onClick={() => void handleDownload()}
              disabled={clamped === 0 || fifoBusy}
            >
              <Download className="h-4 w-4" />
              出库并下载 TXT
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            FIFO 预览
            <Badge variant="fifo">将按此顺序</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="hidden overflow-hidden rounded-xl border border-border md:block">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40">
                  <th className="px-4 py-2.5 text-left font-medium">#</th>
                  <th className="px-4 py-2.5 text-left font-medium">账号</th>
                  <th className="px-4 py-2.5 text-left font-medium">密码</th>
                  <th className="px-4 py-2.5 text-left font-medium">入库时间</th>
                  <th className="px-4 py-2.5 text-left font-medium">备注</th>
                </tr>
              </thead>
              <tbody>
                {preview.map((account, i) => (
                  <tr key={account.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-2.5 text-muted-foreground">
                      {i + 1}
                      {i === 0 && (
                        <Badge variant="fifo" className="ml-1 text-[9px]">
                          队首
                        </Badge>
                      )}
                    </td>
                    <td className="px-4 py-2.5 font-mono">{account.username}</td>
                    <td className="px-4 py-2.5">
                      <PasswordField value={account.password} />
                    </td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">
                      {formatDateTime(account.inboundAt)}
                    </td>
                    <td className="min-w-[140px] px-4 py-2.5">
                      <OutboundNoteField
                        existingNote={account.note}
                        value={
                          fifoNotesByUsername[account.username]?.note ??
                          account.note ??
                          ""
                        }
                        onChange={(note) =>
                          updateFifoNote(account.username, {
                            note,
                            overwriteNote: false,
                          })
                        }
                        overwriteNote={
                          fifoNotesByUsername[account.username]?.overwriteNote ??
                          false
                        }
                        onOverwriteNoteChange={(overwriteNote) =>
                          updateFifoNote(account.username, { overwriteNote })
                        }
                        inputClassName="h-8 text-xs"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="space-y-2 md:hidden">
            {preview.map((account, i) => (
              <div
                key={`${account.id}-mobile`}
                className="rounded-xl border border-border bg-muted/20 px-3 py-2.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-xs font-semibold text-primary">
                      {i + 1}
                    </span>
                    <span className="truncate font-mono text-sm">
                      {account.username}
                    </span>
                  </div>
                  {i === 0 && (
                    <Badge variant="fifo" className="shrink-0 text-[9px]">
                      队首
                    </Badge>
                  )}
                </div>
                <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                  <PasswordField value={account.password} />
                  <p className="whitespace-nowrap">
                    入库 {formatDateTime(account.inboundAt)}
                  </p>
                </div>
                <OutboundNoteField
                  existingNote={account.note}
                  value={
                    fifoNotesByUsername[account.username]?.note ??
                    account.note ??
                    ""
                  }
                  onChange={(note) =>
                    updateFifoNote(account.username, {
                      note,
                      overwriteNote: false,
                    })
                  }
                  overwriteNote={
                    fifoNotesByUsername[account.username]?.overwriteNote ??
                    false
                  }
                  onOverwriteNoteChange={(overwriteNote) =>
                    updateFifoNote(account.username, { overwriteNote })
                  }
                  className="mt-2 w-full"
                  inputClassName="h-8 w-full text-xs"
                />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Modal
        open={resultOpen}
        onClose={() => setResultOpen(false)}
        title="出库成功"
        description={resultMessage}
        footer={
          <>
            <OutboundCopyButton
              clipboardText={clipboardText}
              copying={copying}
              copied={copied}
              onCopy={handleCopy}
            />
            <Button
              variant="secondary"
              onClick={() => {
                setResultOpen(false);
                setQuantity(1);
                setReloadToken((token) => token + 1);
              }}
            >
              再次出库
            </Button>
            <Button onClick={() => setResultOpen(false)}>完成</Button>
          </>
        }
      >
        <div className="max-h-48 space-y-2 overflow-y-auto rounded-xl bg-muted/30 p-3 font-mono text-xs">
          {preview.map((a) => (
            <p key={a.id}>{a.username}----••••</p>
          ))}
        </div>
      </Modal>
    </div>
  );
}
