import React, { useState } from "react";
import { Button } from "./Button.jsx";
/** Pill-shaped command input with an ink Send button. */
export function Composer({ onSend, disabled, placeholder = "Ask Ledger — refund, invoice, compare…" }) {
  const [text, setText] = useState("");
  const submit = (e) => { e.preventDefault(); const t = text.trim(); if (!t || disabled) return; onSend && onSend(t); setText(""); };
  return (
    <form className="ldg-composer" onSubmit={submit}>
      <input aria-label="Command" placeholder={placeholder} value={text} onChange={(e) => setText(e.target.value)} disabled={disabled} />
      <Button type="submit" disabled={disabled || !text.trim()}>{disabled ? "Working…" : "Send"}</Button>
    </form>
  );
}