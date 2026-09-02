import React from "react";
/** Speech bubbles. <UserBubble> is ink-filled, right-aligned. <AssistantBubble> is a card with the tail top-left; tone "confirm" for approvals. */
export function UserBubble({ children }) { return <div className="ldg-user">{children}</div>; }
export function AssistantBubble({ tone = "", children, style }) { return <div className={"ldg-bubble " + tone} style={style}>{children}</div>; }