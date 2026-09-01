import type { AgentEvent } from "./types";

const TOKEN = import.meta.env.OWNER_API_TOKEN ?? "";

export class ApiError extends Error {
  status: number;
  code: string;
  hint: string;

  constructor(status: number, code: string, message: string, hint: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.hint = hint;
  }
}

function headers(extra: Record<string, string> = {}): Record<string, string> {
  return { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json", ...extra };
}

async function raise(response: Response): Promise<never> {
  let code = "http_error", message = response.statusText, hint = "";
  try {
    const body = await response.json();
    code = body.error?.code ?? code; message = body.error?.message ?? message; hint = body.error?.hint ?? "";
  } catch { /* non-JSON error body */ }
  throw new ApiError(response.status, code, message, hint);
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...init, headers: headers((init.headers as Record<string, string>) ?? {}) });
  if (!response.ok) await raise(response);
  return (await response.json()) as T;
}

// POST + SSE. EventSource only speaks GET, so parse the stream by hand:
// frames are separated by a blank line; each has `event:` and `data:` lines.
export async function streamTurn(
  path: string,
  body: unknown,
  onEvent: (event: AgentEvent) => void,
  extraHeaders: Record<string, string> = {},
): Promise<void> {
  const response = await fetch(path, { method: "POST", headers: headers(extraHeaders), body: JSON.stringify(body) });
  if (!response.ok || !response.body) await raise(response);
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    // Normalize \r\n to \n so the parser below is robust regardless of server
    // framing (sse.py sends \n, but this does not assume that stays true).
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let type = "message";
      const dataLines: string[] = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) type = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      // Strict SSE semantics join multi-line data with \n; the backend only ever
      // emits single-line JSON, so this is a no-op in practice.
      const data = dataLines.join("\n");
      if (data) onEvent({ type: type as AgentEvent["type"], data: JSON.parse(data) });
    }
  }
}
