"use client";

import { useMemo, useState } from "react";
import {
  ClipboardPaste,
  Trash2,
  Check,
  Copy,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { parseLines } from "@/lib/parser";
import {
  classifyOutboundLines,
  OUTBOUND_CATEGORY_META,
} from "@/lib/classification";
import {
  getInventoryUsernames,
  getOutboundUsernames,
} from "@/lib/mock-data";
import type { ClassifiedOutboundLine, OutboundCategory } from "@/types/account";

const DEMO_TEXT = `alpha_user01----Pass@2026a----alpha01@mail.example.com
ghost_user----NotInStock----ghost@test.com
old_user01----OldPass01
bad-format-line
alpha_user01----BatchDup----dup@test.com`;

export default function OutboundPastePage() {
  const [text, setText] = useState("");
  const [success, setSuccess] = useState(false);

  const lines = useMemo(() => parseLines(text), [text]);

  const classified = useMemo(() => {
    return classifyOutboundLines(lines, {
      inventoryUsernames: getInventoryUsernames(),
      outboundUsernames: getOutboundUsernames(),
    });
  }, [lines]);

  const grouped = useMemo(() => {
    const groups: Record<OutboundCategory, ClassifiedOutboundLine[]> = {
      inInventory: [],
      notInInventory: [],
      inHistory: [],
      invalid: [],
      batchDuplicate: [],
    };
    for (const item of classified) {
      groups[item.category].push(item);
    }
    return groups;
  }, [classified]);

  const successCount =
    grouped.inInventory.length + grouped.notInInventory.length;

  const copyFailures = () => {
    const failures = classified
      .filter(
        (c) =>
          c.category === "inHistory" ||
          c.category === "invalid" ||
          c.category === "batchDuplicate"
      )
      .map((c) => c.line)
      .join("\n");
    navigator.clipboard.writeText(failures);
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">出库粘贴</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          批量粘贴账号进行出库，状态一目了然
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">粘贴区</CardTitle>
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
              <Button variant="ghost" size="sm" onClick={() => setText(DEMO_TEXT)}>
                演示数据
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="粘贴要出库的账号行…"
              className="min-h-[360px] font-mono text-xs"
            />
            <p className="mt-2 text-xs text-muted-foreground">
              共 {lines.length} 行
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">分类预览</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {(Object.keys(OUTBOUND_CATEGORY_META) as OutboundCategory[]).map(
              (cat) => {
                const meta = OUTBOUND_CATEGORY_META[cat];
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
                      <div className="mt-2 max-h-20 space-y-1 overflow-y-auto">
                        {items.slice(0, 4).map((item) => (
                          <p
                            key={item.line}
                            className="truncate font-mono text-[11px]"
                          >
                            {item.account?.username || item.line.slice(0, 40)}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                );
              }
            )}
          </CardContent>
        </Card>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-card p-4 shadow-sm">
        <Button
          onClick={() => {
            setSuccess(true);
            setTimeout(() => setSuccess(false), 3000);
          }}
          disabled={successCount === 0}
        >
          <Check className="h-4 w-4" />
          确认出库 ({successCount})
        </Button>
        <Button variant="outline" onClick={copyFailures}>
          <Copy className="h-4 w-4" />
          复制失败行
        </Button>
        {success && (
          <span className="text-sm text-emerald-600">出库成功（演示）</span>
        )}
      </div>
    </div>
  );
}
