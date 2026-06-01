"use client";

import { useState } from "react";
import { Minus, Plus, Copy, Check, Package } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { PasswordField } from "@/components/ui/password-field";
import { writeAppClipboardText } from "@/lib/api";
import { mockInventory } from "@/lib/mock-data";
import { formatAccountLine, formatDateTime } from "@/lib/utils";
import Link from "next/link";

export default function OutboundPage() {
  const max = mockInventory.length;
  const [quantity, setQuantity] = useState(1);
  const [copied, setCopied] = useState(false);
  const [resultOpen, setResultOpen] = useState(false);

  const clamped = Math.min(Math.max(quantity, 0), max);
  const preview = mockInventory.slice(0, clamped);
  const chips = [1, 5, 10, max];

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
    await writeAppClipboardText(text);
    setCopied(true);
    setResultOpen(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (max === 0) {
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
          按入库时间先进先出，自动复制到剪贴板
        </p>
        <Badge variant="default" className="mt-3">
          当前库存 {max} 条
        </Badge>
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

          <Button
            className="w-full"
            size="lg"
            onClick={handleOutbound}
            disabled={clamped === 0}
          >
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            出库并复制到剪贴板
          </Button>
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
          <div className="overflow-hidden rounded-xl border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40">
                  <th className="px-4 py-2.5 text-left font-medium">#</th>
                  <th className="px-4 py-2.5 text-left font-medium">账号</th>
                  <th className="px-4 py-2.5 text-left font-medium">密码</th>
                  <th className="px-4 py-2.5 text-left font-medium">入库时间</th>
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
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Modal
        open={resultOpen}
        onClose={() => setResultOpen(false)}
        title="出库成功"
        description={`已出库 ${clamped} 条并复制到剪贴板`}
        footer={
          <>
            <Button variant="secondary" onClick={() => { setResultOpen(false); setQuantity(1); }}>
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
