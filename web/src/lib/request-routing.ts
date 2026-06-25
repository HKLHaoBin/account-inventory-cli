import { fetchLocalCredentials } from "@/lib/local-config";

export type RequestTarget = "local" | "remote";

const LOCAL_ONLY_PREFIXES = [
  "/local/",
  "/api/clipboard/ignore",
  "/api/runtime/",
];

function normalizePath(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

function stripTrailingSlash(value: string): string {
  return value.replace(/\/$/, "");
}

export function resolveRequestTarget(path: string): RequestTarget {
  const normalized = normalizePath(path);
  for (const prefix of LOCAL_ONLY_PREFIXES) {
    if (normalized.startsWith(prefix)) {
      return "local";
    }
  }
  return "remote";
}

export async function resolveRequestBase(path: string): Promise<string> {
  const target = resolveRequestTarget(path);
  if (target === "local") {
    const localBase = process.env.NEXT_PUBLIC_LOCAL_API_BASE_URL ?? "";
    return stripTrailingSlash(localBase);
  }

  const envBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
  if (envBase) {
    return stripTrailingSlash(envBase);
  }

  const credentials = await fetchLocalCredentials();
  if (credentials) {
    if (!credentials.configured) {
      throw new Error("请先配置数据库服务地址");
    }
    if (credentials.cloudApiBaseUrl) {
      return stripTrailingSlash(credentials.cloudApiBaseUrl);
    }
  }

  return "";
}

export async function resolveRequestUrl(path: string): Promise<string> {
  const base = await resolveRequestBase(path);
  return `${base}${normalizePath(path)}`;
}
