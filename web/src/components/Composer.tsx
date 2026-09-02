import { useState, type FormEvent } from "react";
import { Button } from "./Button";

// Pill-shaped command input with an ink Send button. Not sticky: the page is short.
export function Composer({ onSend, disabled }: { onSend: (text: string) => void; disabled: boolean }) {
  const [text, setText] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  };
  return (
    <form className="ldg-composer" onSubmit={submit}>
      <input
        aria-label="Command"
        placeholder="Ask Ledger — refund, invoice, compare…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled}
        autoFocus
      />
      <Button type="submit" disabled={disabled || !text.trim()}>
        {disabled ? "Working…" : "Send"}
      </Button>
    </form>
  );
}
