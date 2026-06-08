export async function readHttpErrorDetail(
  response: Response,
  fallback?: string
): Promise<string> {
  const raw = await response.text();
  const trimmed = raw.trim();
  if (!trimmed) {
    return fallback ?? `请求失败：${response.status}`;
  }

  try {
    const payload = JSON.parse(trimmed) as { detail?: unknown };
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail.trim();
    }
    if (Array.isArray(payload.detail)) {
      const messages = payload.detail
        .map((item) => {
          if (!item || typeof item !== "object") return "";
          const msg = (item as { msg?: unknown }).msg;
          return typeof msg === "string" ? msg.trim() : "";
        })
        .filter(Boolean);
      if (messages.length > 0) {
        return messages.join("；");
      }
    }
  } catch {
    // Fall back to raw response text below.
  }

  return trimmed;
}
