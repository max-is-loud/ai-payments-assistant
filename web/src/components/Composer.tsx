import { useState, type FormEvent } from "react";

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
    <form className="composer" onSubmit={submit}>
      <input
        aria-label="Command"
        placeholder="Refund Maya's last payment"
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled}
        autoFocus
      />
      <button className="btn primary" type="submit" disabled={disabled || !text.trim()}>
        {disabled ? "Working…" : "Send"}
      </button>
    </form>
  );
}
