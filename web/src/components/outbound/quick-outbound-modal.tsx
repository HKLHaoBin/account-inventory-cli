"use client";

import { useEffect, useMemo, useState } from "react";
import { Minus, Plus, Download, Upload } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { BatchNoteControls } from "@/components/notes/batch-note-controls";
import { OutboundNoteField } from "@/components/notes/outbound-note-field";
import { OutboundCopyButton } from "@/components/outbound/outbound-copy-button";
import { ClipboardCopyFallback } from "@/components/clipboard/clipboard-copy-fallback";
import { useLastOutboundClipboard } from "@/hooks/use-last-outbound-clipboard";
import { commitFifo, previewFifo } from "@/lib/api";
import { downloadTextFile } from "@/lib/download";
import type { Account, FifoNoteEntry } from "@/types/account";

interface QuickOutboundModalProps {
  open: boolean;
  onClose: () => void;
  onNavigate?: () => void;
}

export function QuickOutboundModal({
  open,
  onClose,
  onNavigate,
}: QuickOutboundModalProps) {
  const [quantity, setQuantity] = useState(1);
  const [success, setSuccess] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");
  const [max, setMax] = useState(0);
  const [preview, setPreview] = useState<Account[]>([]);
  const [fifoNotes, setFifoNotes] = useState<FifoNoteEntry[]>([]);
  const [message, setMessage] = useState("");
  const [reloadToken, setReloadToken] = useState(0);
  const [busy, setBusy] = useState(false);
  const {
    clipboardText,
    remember,
    clear: clearClipboard,
    copy,
    copying,
    copied,
    copyFailed,
    acknowledgeCopySuccess,
  } = useLastOutboundClipboard();

  const clamped = Math.min(Math.max(quantity, 0), max);

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
    if (!open) return;
    let ignore = false;
    async function loadPreview() {
      try {
        const payload = await previewFifo(quantity);
        if (ignore) return;
        setMax(payload.max);
        setPreview(payload.rows);
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
        setMessage("");
      } catch (error) {
        if (ignore) return;
        setMessage(error instanceof Error ? error.message : "FIFO 预览失败");
      }
    }
    void loadPreview();
    return () => {
      ignore = true;
    };
  }, [open, quantity, reloadToken]);

  useEffect(() => {
    if (!open) return;
    clearClipboard();
  }, [open, quantity, clearClipboard]);

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
    if (clamped === 0 || busy) return;
    setBusy(true);
    setMessage("");
    try {
      const payload = await commitFifo(quantity, fifoNotes);
      const text = payload.clipboardText ?? "";
      remember(text);
      const copiedOk = text ? await copy(text) : true;
      setPreview([]);
      setSuccess(true);
      setSuccessMessage(
        copiedOk
          ? `已出库 ${payload.quantity} 条并复制到剪贴板`
          : `已出库 ${payload.quantity} 条，自动复制失败，请手动复制`
      );
      setReloadToken((token) => token + 1);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "FIFO 出库失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleDownload() {
    if (clamped === 0 || busy) return;
    setBusy(true);
    setMessage("");
    try {
      const payload = await commitFifo(quantity, fifoNotes);
      remember(payload.clipboardText ?? "");
      if (payload.clipboardText) {
        downloadTextFile(payload.clipboardText);
      }
      setPreview([]);
      setSuccess(true);
      setSuccessMessage(`已出库 ${payload.quantity} 条并下载 TXT`);
      setReloadToken((token) => token + 1);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "FIFO 出库失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleCopy() {
    setMessage("");
    const ok = await copy();
    if (!ok && clipboardText) {
      setMessage("自动复制失败，请使用下方手动复制");
    }
  }

  const resetSuccess = () => {
    setSuccess(false);
    setSuccessMessage("");
    setQuantity(1);
    clearClipboard();
    setReloadToken((token) => token + 1);
  };

  const chips = Array.from(new Set([1, 5, 10, max].filter((n) => n > 0)));

  return (
    <Modal
      open={open}
      onClose={() => {
        onClose();
        setSuccess(false);
        setSuccessMessage("");
        setQuantity(1);
        setMessage("");
        clearClipboard();
        setReloadToken(0);
      }}
      title={success ? "出库成功" : "快捷 FIFO 出库"}
      description={
        success
          ? successMessage
          : `当前库存 ${max} 条，将按 FIFO 顺序出库`
      }
      className="max-w-md"
      footer={
        success ? (
          <>
            <OutboundCopyButton
              clipboardText={clipboardText}
              copying={copying}
              copied={copied}
              onCopy={handleCopy}
            />
            <Button variant="secondary" onClick={resetSuccess}>
              再次出库
            </Button>
            <Button
              onClick={() => {
                resetSuccess();
                onClose();
              }}
            >
              完成
            </Button>
          </>
        ) : (
          <div className="flex w-full flex-wrap justify-end gap-2">
            <Button variant="secondary" onClick={onNavigate}>
              前往出库页
            </Button>
            <Button
              variant="secondary"
              onClick={() => void handleDownload()}
              disabled={max === 0 || clamped === 0 || busy}
            >
              <Download className="h-4 w-4" />
              下载 TXT
            </Button>
            <OutboundCopyButton
              clipboardText={clipboardText}
              copying={copying}
              copied={copied}
              onCopy={handleCopy}
              disabled={busy}
            />
            <Button
              onClick={() => void handleCommit()}
              disabled={max === 0 || clamped === 0 || busy}
            >
              <Upload className="h-4 w-4" />
              出库并复制
            </Button>
          </div>
        )
      }
    >
      {!success && (
        <div className="space-y-4">
          <div className="flex items-center justify-center gap-4">
            <Button
              variant="outline"
              size="icon"
              onClick={() => setQuantity((q) => Math.max(0, q - 1))}
              disabled={clamped <= 0 || busy}
            >
              <Minus className="h-4 w-4" />
            </Button>
            <input
              type="number"
              value={quantity}
              onChange={(e) => setQuantity(Number(e.target.value))}
              className="w-20 rounded-xl border border-border bg-background px-3 py-2 text-center text-2xl font-bold focus:outline-none focus:ring-2 focus:ring-primary/30"
              min={0}
              max={max}
            />
            <Button
              variant="outline"
              size="icon"
              onClick={() => setQuantity((q) => Math.min(max, q + 1))}
              disabled={clamped >= max || busy}
            >
              <Plus className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex flex-wrap justify-center gap-2">
            {chips.map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => setQuantity(n)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-all ${
                  clamped === n
                    ? "bg-primary text-primary-foreground shadow-sm"
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

          {message && (
            <p className="text-center text-sm text-red-600">{message}</p>
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
            disabled={busy}
          />

          <div className="rounded-xl border border-border bg-muted/30 p-3">
            <p className="mb-2 text-xs font-medium text-muted-foreground">FIFO 预览</p>
            <div className="space-y-1.5">
              {preview.slice(0, 3).map((a, i) => (
                <div key={a.id} className="space-y-1 text-sm">
                  <div className="flex items-center gap-2">
                    {i === 0 && <Badge variant="fifo" className="text-[10px]">队首</Badge>}
                    <span className="font-mono">{a.username}</span>
                  </div>
                  <OutboundNoteField
                    existingNote={a.note}
                    value={
                      fifoNotesByUsername[a.username]?.note ?? a.note ?? ""
                    }
                    onChange={(note) =>
                      updateFifoNote(a.username, {
                        note,
                        overwriteNote: false,
                      })
                    }
                    overwriteNote={
                      fifoNotesByUsername[a.username]?.overwriteNote ?? false
                    }
                    onOverwriteNoteChange={(overwriteNote) =>
                      updateFifoNote(a.username, { overwriteNote })
                    }
                    disabled={busy}
                    inputClassName="h-8 text-xs"
                  />
                </div>
              ))}
              {preview.length > 3 && (
                <p className="text-xs text-muted-foreground">
                  +{preview.length - 3} 条更多…
                </p>
              )}
            </div>
          </div>
        </div>
      )}
      {success && (
        <ClipboardCopyFallback
          visible={copyFailed}
          text={clipboardText}
          onRetry={handleCopy}
          onCopied={acknowledgeCopySuccess}
        />
      )}
    </Modal>
  );
}
