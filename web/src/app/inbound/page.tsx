"use client";

import { useMemo, useState } from "react";
import {
  ClipboardPaste,
  Trash2,
  FileText,
  Check,
  Copy,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { parseLines } from "@/lib/parser";
import {
  classifyInboundLines,
  INBOUND_CATEGORY_META,
} from "@/lib/classification";
import {
  getInventoryUsernames,
  getOutboundUsernames,
  getOutboundTimes,
  SAMPLE_FORMAT,
} from "@/lib/mock-data";
import { formatDateTime } from "@/lib/utils";
import type { ClassifiedInboundLine, InboundCategory } from "@/types/account";

const DEMO_TEXT = `new_user_a----PassA123----newa@mail.com----MailA----https://new.example.com
alpha_user01----DupPass----dup@test.com
returned_user----ReturnPass----ret@test.com----RetMail
badline-only-one-field
new_user_b----PassB456
returned_user----BatchDup----dup2@test.com`;

export default function InboundPage() {
  const [text, setText] = useState("");
  const [pendingOpen, setPendingOpen] = useState(false);
  const [approvedPending, setApprovedPending] = useState<Set<string>>(new Set());
  const [success, setSuccess] = useState(false);

  const lines = useMemo(() => parseLines(text), [text]);

  const classified = useMemo(() => {
    return classifyInboundLines(lines, {
      inventoryUsernames: getInventoryUsernames(),
      outboundUsernames: getOutboundUsernames(),
      outboundTimes: getOutboundTimes(),
    });
  }, [lines]);

  const grouped = useMemo(() => {
    const groups: Record<InboundCategory, ClassifiedInboundLine[]> = {
      ready: [],
      duplicate: [],
      pending: [],
      invalid: [],
      batchDuplicate: [],
    };
    for (const item of classified) {
      groups[item.category].push(item);
    }
    return groups;
  }, [classified]);

  const readyCount = grouped.ready.length;
  const pendingItems = grouped.pending;
  const hasPending = pendingItems.length > 0;
  const approvedReady =
    readyCount +
    pendingItems.filter((p) => approvedPending.has(p.line)).length;

  const borderColor =
    lines.length === 0
      ? "border-border"
      : grouped.invalid.length > 0 || grouped.duplicate.length > 0
        ? "border-red-300 dark:border-red-800"
        : "border-emerald-300 dark:border-emerald-800";

  const handleConfirm = () => {
    if (hasPending && approvedPending.size < pendingItems.length) {
      setPendingOpen(true);
      return;
    }
    setSuccess(true);
    setTimeout(() => setSuccess(false), 3000);
  };

  const copyFailures = () => {
    const failures = classified
      .filter((c) => c.category !== "ready" && c.category !== "pending")
      .map((c) => c.line)
      .join("\n");
    navigator.clipboard.writeText(failures);
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">入库</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          粘贴多行账号，实时分类预览
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        <Card className="flex flex-col">
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">输入区</CardTitle>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => navigator.clipboard.readText().then(setText)}
              >
                <ClipboardPaste className="h-4 w-4" />
                从剪贴板粘贴
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setText("")}>
                <Trash2 className="h-4 w-4" />
                清空
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setText(SAMPLE_FORMAT)}
              >
                <FileText className="h-4 w-4" />
                示例格式
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setText(DEMO_TEXT)}
              >
                演示数据
              </Button>
            </div>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col">
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="粘贴账号行，每行一条&#10;格式：账号----密码----邮箱----邮箱密码----网址"
              className={`min-h-[360px] flex-1 font-mono text-xs ${borderColor} border-2`}
            />
            <p className="mt-2 text-xs text-muted-foreground">
              共 {lines.length} 行 ·{" "}
              {grouped.invalid.length > 0
                ? `${grouped.invalid.length} 行格式错误`
                : "语法校验通过"}
            </p>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">分类预览</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {(Object.keys(INBOUND_CATEGORY_META) as InboundCategory[]).map(
                (cat) => {
                  const meta = INBOUND_CATEGORY_META[cat];
                  const items = grouped[cat];
                  return (
                    <div
                      key={cat}
                      className={`rounded-xl border p-3 ${meta.bg} dark:bg-opacity-20`}
                    >
                      <div className="flex items-center justify-between">
                        <span className={`text-sm font-medium ${meta.color}`}>
                          {meta.label}
                        </span>
                        <Badge variant="secondary">{items.length}</Badge>
                      </div>
                      {items.length > 0 && (
                        <div className="mt-2 max-h-24 space-y-1 overflow-y-auto">
                          {items.slice(0, 5).map((item) => (
                            <p
                              key={item.line}
                              className="truncate font-mono text-[11px] text-muted-foreground"
                              title={item.reason || item.line}
                            >
                              {item.account?.username || item.line.slice(0, 40)}
                              {item.reason && (
                                <span className="ml-1 text-red-600">
                                  — {item.reason}
                                </span>
                              )}
                            </p>
                          ))}
                          {items.length > 5 && (
                            <p className="text-[11px] text-muted-foreground">
                              +{items.length - 5} 条更多
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  );
                }
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-card p-4 shadow-sm">
        <Button onClick={handleConfirm} disabled={readyCount === 0 && !hasPending}>
          <Check className="h-4 w-4" />
          确认入库 ({approvedReady || readyCount})
        </Button>
        {hasPending && (
          <Button variant="secondary" onClick={() => setPendingOpen(true)}>
            待确认 ({pendingItems.length})
          </Button>
        )}
        <Button
          variant="outline"
          onClick={copyFailures}
          disabled={
            grouped.duplicate.length +
              grouped.invalid.length +
              grouped.batchDuplicate.length ===
            0
          }
        >
          <Copy className="h-4 w-4" />
          复制失败行
        </Button>
        {success && (
          <span className="flex items-center gap-1 text-sm text-emerald-600">
            <Check className="h-4 w-4" /> 入库成功（演示）
          </span>
        )}
      </div>

      <Modal
        open={pendingOpen}
        onClose={() => setPendingOpen(false)}
        title="曾出库账号 — 待确认"
        description="以下账号曾在出库历史中出现，请勾选批准重新入库"
        className="max-w-lg"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setApprovedPending(new Set(pendingItems.map((p) => p.line)));
                setPendingOpen(false);
              }}
            >
              全部批准
            </Button>
            <Button
              onClick={() => {
                setPendingOpen(false);
                setSuccess(true);
              }}
              disabled={approvedPending.size === 0}
            >
              批准选中 ({approvedPending.size})
            </Button>
          </>
        }
      >
        <div className="max-h-64 space-y-2 overflow-y-auto">
          {pendingItems.map((item) => (
            <label
              key={item.line}
              className="flex cursor-pointer items-start gap-3 rounded-xl border border-border p-3 hover:bg-muted/50"
            >
              <input
                type="checkbox"
                checked={approvedPending.has(item.line)}
                onChange={(e) => {
                  setApprovedPending((prev) => {
                    const next = new Set(prev);
                    if (e.target.checked) next.add(item.line);
                    else next.delete(item.line);
                    return next;
                  });
                }}
                className="mt-1"
              />
              <div>
                <p className="font-mono text-sm">{item.account?.username}</p>
                {item.lastOutboundAt && (
                  <p className="text-xs text-muted-foreground">
                    最近出库：{formatDateTime(item.lastOutboundAt)}
                  </p>
                )}
              </div>
            </label>
          ))}
        </div>
      </Modal>
    </div>
  );
}
