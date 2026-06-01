"use client";

import { useState } from "react";
import { Minus, Plus, Copy, Check } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { mockInventory } from "@/lib/mock-data";
import { formatAccountLine } from "@/lib/utils";

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
  const max = mockInventory.length;
  const [quantity, setQuantity] = useState(1);
  const [copied, setCopied] = useState(false);
  const [success, setSuccess] = useState(false);

  const clamped = Math.min(Math.max(quantity, 0), max);
  const preview = mockInventory.slice(0, clamped);

  const handleOutbound = async () => {
    if (clamped === 0) return;
    const text = preview
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
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setSuccess(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const chips = [1, 5, 10, max];

  return (
    <Modal
      open={open}
      onClose={() => {
        onClose();
        setSuccess(false);
        setQuantity(1);
      }}
      title={success ? "出库成功" : "快捷 FIFO 出库"}
      description={
        success
          ? `已出库 ${clamped} 条并复制到剪贴板`
          : `当前库存 ${max} 条，将按 FIFO 顺序出库`
      }
      className="max-w-md"
      footer={
        success ? (
          <>
            <Button variant="secondary" onClick={() => { setSuccess(false); setQuantity(1); }}>
              再次出库
            </Button>
            <Button onClick={onClose}>完成</Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={onNavigate}>
              前往出库页
            </Button>
            <Button onClick={handleOutbound} disabled={max === 0 || clamped === 0}>
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              出库并复制
            </Button>
          </>
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
              disabled={clamped <= 0}
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
              disabled={clamped >= max}
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

          <div className="rounded-xl border border-border bg-muted/30 p-3">
            <p className="mb-2 text-xs font-medium text-muted-foreground">FIFO 预览</p>
            <div className="space-y-1.5">
              {preview.slice(0, 3).map((a, i) => (
                <div key={a.id} className="flex items-center gap-2 text-sm">
                  {i === 0 && <Badge variant="fifo" className="text-[10px]">队首</Badge>}
                  <span className="font-mono">{a.username}</span>
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
    </Modal>
  );
}
