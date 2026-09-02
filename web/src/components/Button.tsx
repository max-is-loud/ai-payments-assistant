import type { ButtonHTMLAttributes, ReactNode } from "react";

// Pill button. Primary is solid ink, secondary a hairline, danger a small
// coral outline used only beside an error.
export function Button({ variant = "primary", block = false, size = "", className = "", type = "button", children, ...rest }: {
  variant?: "primary" | "secondary" | "danger";
  block?: boolean;
  size?: "" | "lg";
  children: ReactNode;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  const cls = ["ldg-btn", variant === "primary" ? "" : variant, block ? "block" : "", size, className]
    .filter(Boolean)
    .join(" ");
  return (
    <button type={type} className={cls} {...rest}>
      {children}
    </button>
  );
}
