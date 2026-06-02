import { parseAccountLine } from "./parser";
import type {
  ClassifiedInboundLine,
  ClassifiedOutboundLine,
  InboundCategory,
  OutboundCategory,
} from "@/types/account";

interface InboundContext {
  inventoryUsernames: Set<string>;
  outboundUsernames: Set<string>;
  outboundTimes: Map<string, string>;
}

interface OutboundContext {
  inventoryUsernames: Set<string>;
  outboundUsernames: Set<string>;
}

export function classifyInboundLines(
  lines: string[],
  ctx: InboundContext,
  separators?: string[]
): ClassifiedInboundLine[] {
  const seen = new Set<string>();
  return lines.map((line) => {
    try {
      const account = parseAccountLine(line, separators);
      const { username } = account;

      if (ctx.inventoryUsernames.has(username)) {
        return {
          line,
          category: "duplicate" as InboundCategory,
          reason: `账号 ${username} 已在库存中`,
          account,
        };
      }

      if (seen.has(username)) {
        return {
          line,
          category: "batchDuplicate" as InboundCategory,
          reason: "本批次内账号重复",
          account,
        };
      }
      seen.add(username);

      if (ctx.outboundUsernames.has(username)) {
        return {
          line,
          category: "pending" as InboundCategory,
          account,
          lastOutboundAt: ctx.outboundTimes.get(username),
        };
      }

      return { line, category: "ready" as InboundCategory, account };
    } catch (e) {
      return {
        line,
        category: "invalid" as InboundCategory,
        reason: e instanceof Error ? e.message : "格式错误",
      };
    }
  });
}

export function classifyOutboundLines(
  lines: string[],
  ctx: OutboundContext,
  separators?: string[]
): ClassifiedOutboundLine[] {
  const seen = new Set<string>();
  return lines.map((line) => {
    try {
      const account = parseAccountLine(line, separators);
      const { username } = account;

      if (seen.has(username)) {
        return {
          line,
          category: "batchDuplicate" as OutboundCategory,
          reason: "本批次内账号重复",
          account,
        };
      }
      seen.add(username);

      if (
        ctx.outboundUsernames.has(username) &&
        !ctx.inventoryUsernames.has(username)
      ) {
        return {
          line,
          category: "inHistory" as OutboundCategory,
          reason: "已在出库记录中",
          account,
        };
      }

      if (ctx.inventoryUsernames.has(username)) {
        return {
          line,
          category: "inInventory" as OutboundCategory,
          account,
        };
      }

      return {
        line,
        category: "notInInventory" as OutboundCategory,
        account,
      };
    } catch (e) {
      return {
        line,
        category: "invalid" as OutboundCategory,
        reason: e instanceof Error ? e.message : "格式错误",
      };
    }
  });
}

export const INBOUND_CATEGORY_META: Record<
  InboundCategory,
  { label: string; color: string; bg: string }
> = {
  ready: { label: "可入库", color: "text-emerald-700", bg: "bg-emerald-50 border-emerald-200" },
  duplicate: { label: "库存重复", color: "text-red-700", bg: "bg-red-50 border-red-200" },
  pending: { label: "曾出库待确认", color: "text-amber-700", bg: "bg-amber-50 border-amber-200" },
  invalid: { label: "格式错误", color: "text-slate-600", bg: "bg-slate-50 border-slate-200" },
  batchDuplicate: { label: "批次内重复", color: "text-orange-700", bg: "bg-orange-50 border-orange-200" },
};

export const OUTBOUND_CATEGORY_META: Record<
  OutboundCategory,
  { label: string; color: string; bg: string }
> = {
  inInventory: { label: "在库存中", color: "text-blue-700", bg: "bg-blue-50 border-blue-200" },
  notInInventory: { label: "不在库存", color: "text-violet-700", bg: "bg-violet-50 border-violet-200" },
  inHistory: { label: "已在历史", color: "text-red-700", bg: "bg-red-50 border-red-200" },
  invalid: { label: "格式错误", color: "text-slate-600", bg: "bg-slate-50 border-slate-200" },
  batchDuplicate: { label: "批次内重复", color: "text-orange-700", bg: "bg-orange-50 border-orange-200" },
};
