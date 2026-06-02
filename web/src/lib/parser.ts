import type { ParsedAccount } from "@/types/account";

const DEFAULT_SEPARATORS = ["----"];

function _parseWithSeparator(line: string, separator: string): ParsedAccount {
  const parts = line.split(separator).map((p) => p.trim());
  if (parts.length < 2) {
    throw new Error("格式错误：至少需要「账号与密码」两段");
  }
  if (parts.length > 5) {
    throw new Error(
      "格式错误：最多 5 段（账号、密码、邮箱、邮箱密码、网址）"
    );
  }

  const [username, password] = parts;
  if (!username) throw new Error("账号不能为空");
  if (!password) throw new Error("密码不能为空");

  let email: string | undefined;
  let emailPassword: string | undefined;
  let url: string | undefined;

  if (parts.length === 4 && !parts[2]) {
    url = parts[3] || undefined;
  } else {
    if (parts.length >= 3) email = parts[2] || undefined;
    if (parts.length >= 4) emailPassword = parts[3] || undefined;
    if (parts.length >= 5) url = parts[4] || undefined;
  }

  return { username, password, email, emailPassword, url, line };
}

export function parseAccountLine(
  line: string,
  separators?: string[]
): ParsedAccount {
  const stripped = line.trim();
  if (!stripped) throw new Error("输入不能为空");

  const seps = separators === undefined ? DEFAULT_SEPARATORS : separators;
  if (seps.length === 0) {
    throw new Error("当前没有启用的分隔规则");
  }
  let lastError: Error | null = null;

  for (const separator of seps) {
    try {
      return _parseWithSeparator(stripped, separator);
    } catch (error) {
      lastError = error instanceof Error ? error : new Error("格式错误");
    }
  }

  throw lastError ?? new Error("格式错误");
}

export function parseLines(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
}
