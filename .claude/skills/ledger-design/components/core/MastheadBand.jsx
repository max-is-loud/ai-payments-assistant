import React from "react";
/** Full-width ink band. wordmark + tag left; status + date right. */
export function MastheadBand({ wordmark = "Ledger", tag = "payments assistant", status, date }) {
  return (
    <header className="ldg-band">
      <div style={{ display: "flex", alignItems: "baseline" }}><span className="wordmark">{wordmark}</span><span className="tag">{tag}</span></div>
      <div className="meta">{status && <span><i className="ldg-dot"></i>{status}</span>}<span>{date}</span></div>
    </header>
  );
}