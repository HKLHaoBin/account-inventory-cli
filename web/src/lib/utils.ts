import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatAccountLine(
  username: string,
  password: string,
  email?: string,
  emailPassword?: string,
  url?: string
): string {
  if (!email && !emailPassword && !url) {
    return `${username}----${password}`;
  }
  if (url && !email && !emailPassword) {
    return `${username}----${password}--------${url}`;
  }
  if (!url) {
    return [username, password, email ?? "", emailPassword ?? ""].join("----");
  }
  return [username, password, email ?? "", emailPassword ?? "", url ?? ""].join(
    "----"
  );
}

export function maskValue(value: string, visible = 2): string {
  if (value.length <= visible * 2) return "••••••";
  return value.slice(0, visible) + "••••" + value.slice(-visible);
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "昨天";
  return `${days} 天前`;
}

export function groupByDate<T>(
  records: T[],
  dateKey: keyof T
): { label: string; items: T[] }[] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  const groups: Record<string, T[]> = {
    今天: [],
    昨天: [],
    更早: [],
  };

  for (const record of records) {
    const raw = record[dateKey];
    if (typeof raw !== "string") continue;
    const d = new Date(raw);
    d.setHours(0, 0, 0, 0);
    if (d.getTime() === today.getTime()) groups["今天"].push(record);
    else if (d.getTime() === yesterday.getTime()) groups["昨天"].push(record);
    else groups["更早"].push(record);
  }

  return Object.entries(groups)
    .filter(([, items]) => items.length > 0)
    .map(([label, items]) => ({ label, items }));
}
