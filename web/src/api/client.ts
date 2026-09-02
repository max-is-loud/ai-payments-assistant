import type { AgentEvent } from "./types";

const TOKEN = import.meta.env.OWNER_API_TOKEN ?? "";

export class ApiError extends Error {
  status: number;
  code: string;
  hint: string;
  detail: string;

  constructor(status: number, code: string, message: string, hint: string, detail = "") {
    super(message);
    this.status = status;
    this.code = code;
    this.hint = hint;
    this.detail = detail;
  }
}

function headers(extra: Record<string, string> = {}): Record<string, string> {
  return { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json", ...extra };
}

async function raise(response: Response): Promise<never> {
  // Every API failure is `{error: {code, message, hint}}`, so anything else came
  // from in front of the API (the dev proxy with nothing listening behind it).
  // The status is then all there is to report, in words rather than statusText.
  let code = "http_error", hint = "", detail = "";
  let message = `The assistant API didn't answer (HTTP ${response.status}). Is it running?`;
  try {
    const body = await response.json();
    if (body?.error?.message) {
      code = body.error.code ?? code; message = body.error.message;
      hint = body.error.hint ?? ""; detail = body.error.detail ?? "";
    }
  } catch { /* non-JSON error body */ }
  throw new ApiError(response.status, code, message, hint, detail);
}

// One sentence for the owner. `detail` is only ever set when the API runs with
// DEBUG=1, and goes on its own line so it reads as the developer note it is.
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    const text = error.hint ? `${error.message} ${error.hint}` : error.message;
    return error.detail ? `${text}\n${error.detail}` : text;
  }
  // fetch rejects with a TypeError when the request never got a response at all.
  if (error instanceof TypeError) return "Couldn't reach the assistant API. Is it running?";
  return error instanceof Error ? error.message : String(error);
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
