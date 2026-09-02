import React from "react";
import { Button } from "./Button.jsx";
/** Coral left-rule strip. One sentence + Retry. Developer detail never goes here (it goes behind DEBUG in the trail). */
export function ErrorStrip({ children, onRetry }) {
  return <div className="ldg-error"><span>{children}</span>{onRetry && <Button variant="danger" onClick={onRetry}>Retry</Button>}</div>;
}