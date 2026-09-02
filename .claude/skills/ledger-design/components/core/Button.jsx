import React from "react";
/** variant: "primary" (ink pill) | "secondary" (hairline pill) | "danger" (coral outline, small). block = full width. */
export function Button({ variant = "primary", block = false, size = "", disabled, onClick, children, type = "button" }) {
  const cls = ["ldg-btn", variant === "primary" ? "" : variant, block ? "block" : "", size].join(" ");
  return <button type={type} className={cls} disabled={disabled} onClick={onClick}>{children}</button>;
}