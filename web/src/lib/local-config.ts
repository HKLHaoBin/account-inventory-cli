import { readHttpErrorDetail } from "@/lib/http-error";

export interface LocalConfigPayload {
  cloudApiBaseUrl: string | null;
  configured: boolean;
}

async function requestLocalJson<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (response.status === 404) {
    throw new Error("NOT_FOUND");
  }

  if (!response.ok) {
    const detail = await readHttpErrorDetail(response);
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

export async function fetchLocalConfig(): Promise<LocalConfigPayload | null> {
  try {
    return await requestLocalJson<LocalConfigPayload>("/local/config");
  } catch (error) {
    if (error instanceof Error && error.message === "NOT_FOUND") {
      return null;
    }
    throw error;
  }
}

export function saveLocalConfig(
  cloudApiBaseUrl: string
): Promise<LocalConfigPayload> {
  return requestLocalJson<LocalConfigPayload>("/local/config", {
    method: "PUT",
    body: JSON.stringify({ cloudApiBaseUrl }),
  });
}

export function testLocalConfig(): Promise<{ ok: boolean }> {
  return requestLocalJson<{ ok: boolean }>("/local/config/test", {
    method: "POST",
  });
}
