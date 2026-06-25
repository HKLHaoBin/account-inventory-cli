"use client";

import type { ReactNode } from "react";
import { PasswordField } from "@/components/ui/password-field";
import { OutboundNoteField } from "@/components/notes/outbound-note-field";
import { formatDateTime } from "@/lib/utils";
import type { SearchResult } from "@/types/account";

export const ACCOUNT_SEARCH_PLACEHOLDER = "搜索账号、密码、邮箱、网址、备注…";

export type AccountFieldKey =
  | "username"
  | "password"
  | "email"
  | "emailPassword"
  | "url"
  | "note"
  | "inboundAt"
  | "outboundAt";

export type AccountFieldKind =
  | "text"
  | "password"
  | "datetime"
  | "note"
  | "outboundNote";

export interface AccountColumnDef {
  key: AccountFieldKey;
  label: string;
  kind: AccountFieldKind;
}

export type AccountLike = {
  username?: string | null;
  password?: string | null;
  email?: string | null;
  emailPassword?: string | null;
  url?: string | null;
  note?: string | null;
  inboundAt?: string | null;
  outboundAt?: string | null;
};

export const STANDARD_ACCOUNT_DATA_COLUMNS: AccountColumnDef[] = [
  { key: "username", label: "账号", kind: "text" },
  { key: "password", label: "密码", kind: "password" },
  { key: "email", label: "邮箱", kind: "password" },
  { key: "emailPassword", label: "邮箱密码", kind: "password" },
  { key: "url", label: "网址", kind: "text" },
  { key: "note", label: "备注", kind: "note" },
];

export const INVENTORY_ACCOUNT_COLUMNS: AccountColumnDef[] = [
  ...STANDARD_ACCOUNT_DATA_COLUMNS,
  { key: "inboundAt", label: "入库时间", kind: "datetime" },
];

export const OUTBOUND_RECORD_COLUMNS: AccountColumnDef[] = [
  ...STANDARD_ACCOUNT_DATA_COLUMNS,
  { key: "inboundAt", label: "入库时间", kind: "datetime" },
  { key: "outboundAt", label: "出库时间", kind: "datetime" },
];

export const FIFO_PREVIEW_COLUMNS: AccountColumnDef[] = [
  { key: "username", label: "账号", kind: "text" },
  { key: "password", label: "密码", kind: "password" },
  { key: "email", label: "邮箱", kind: "password" },
  { key: "emailPassword", label: "邮箱密码", kind: "password" },
  { key: "url", label: "网址", kind: "text" },
  { key: "inboundAt", label: "入库时间", kind: "datetime" },
  { key: "note", label: "备注", kind: "outboundNote" },
];

export const INBOUND_PREVIEW_COLUMNS: AccountColumnDef[] = [
  { key: "username", label: "账号", kind: "text" },
  { key: "password", label: "密码", kind: "password" },
  { key: "email", label: "邮箱", kind: "password" },
  { key: "emailPassword", label: "邮箱密码", kind: "password" },
  { key: "url", label: "网址", kind: "text" },
  { key: "note", label: "备注", kind: "outboundNote" },
];

export const OUTBOUND_PASTE_COLUMNS: AccountColumnDef[] = [
  { key: "username", label: "账号", kind: "text" },
  { key: "password", label: "密码", kind: "password" },
  { key: "email", label: "邮箱", kind: "password" },
  { key: "emailPassword", label: "邮箱密码", kind: "password" },
  { key: "url", label: "网址", kind: "text" },
  { key: "note", label: "备注", kind: "outboundNote" },
];

function renderEmpty() {
  return <span className="text-muted-foreground">—</span>;
}

function fieldValue(record: AccountLike, key: AccountFieldKey): string | null | undefined {
  return record[key];
}

export interface AccountFieldCellProps {
  column: AccountColumnDef;
  record: AccountLike;
  className?: string;
  noteValue?: string;
  onNoteChange?: (note: string) => void;
  overwriteNote?: boolean;
  onOverwriteNoteChange?: (overwrite: boolean) => void;
  existingNote?: string | null;
}

export function AccountFieldCell({
  column,
  record,
  className,
  noteValue,
  onNoteChange,
  overwriteNote,
  onOverwriteNoteChange,
  existingNote,
}: AccountFieldCellProps): ReactNode {
  const value = fieldValue(record, column.key);

  switch (column.kind) {
    case "password":
      return value ? (
        <PasswordField value={value} className={className} />
      ) : (
        renderEmpty()
      );
    case "datetime":
      return value ? (
        <span className="text-xs text-muted-foreground whitespace-nowrap">
          {formatDateTime(value)}
        </span>
      ) : (
        renderEmpty()
      );
    case "note":
      return value?.trim() ? (
        <span className="break-words whitespace-pre-wrap text-xs text-muted-foreground">
          {value}
        </span>
      ) : (
        renderEmpty()
      );
    case "outboundNote":
      if (onNoteChange) {
        return (
          <OutboundNoteField
            existingNote={existingNote ?? record.note}
            value={noteValue ?? record.note ?? ""}
            onChange={onNoteChange}
            overwriteNote={overwriteNote ?? false}
            onOverwriteNoteChange={onOverwriteNoteChange ?? (() => undefined)}
            inputClassName="h-8 text-xs"
          />
        );
      }
      return value?.trim() ? (
        <span className="break-words whitespace-pre-wrap text-xs text-muted-foreground">
          {value}
        </span>
      ) : (
        renderEmpty()
      );
    case "text":
    default:
      if (column.key === "username") {
        return value ? (
          <span className="font-mono">{value}</span>
        ) : (
          renderEmpty()
        );
      }
      if (column.key === "url") {
        return value ? (
          <span className="max-w-[140px] truncate text-xs text-blue-600">{value}</span>
        ) : (
          renderEmpty()
        );
      }
      return value ? (
        <span className="font-mono text-xs">{value}</span>
      ) : (
        renderEmpty()
      );
  }
}

export function AccountColumnHeader({
  column,
  className = "px-4 py-3 text-left font-medium",
}: {
  column: AccountColumnDef;
  className?: string;
}) {
  return <th className={className}>{column.label}</th>;
}

export function searchSourceBadge(source: SearchResult["source"]): {
  variant: "inventory" | "outbound" | "inbound";
  label: string;
} {
  switch (source) {
    case "inventory":
      return { variant: "inventory", label: "库存" };
    case "outbound":
      return { variant: "outbound", label: "出库" };
    case "inbound":
      return { variant: "inbound", label: "历史" };
  }
}

export function searchResultTimestamp(result: SearchResult): string | null {
  if (result.source === "outbound") {
    return result.account.outboundAt;
  }
  return result.account.inboundAt;
}
