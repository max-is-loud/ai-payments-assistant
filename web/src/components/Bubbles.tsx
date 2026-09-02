import type { HTMLAttributes, ReactNode } from "react";

// The owner's words: solid ink, right-aligned, tail bottom-right.
export function UserBubble({ children }: { children: ReactNode }) {
  return <div className="ldg-user">{children}</div>;
}

// The assistant's: a card with the tail top-left. `confirm` turns it amber.
export function AssistantBubble({ tone = "", children, ...rest }: {
  tone?: "" | "confirm";
  children: ReactNode;
} & HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={["ldg-bubble", tone].filter(Boolean).join(" ")} {...rest}>
      {children}
    </div>
  );
}
