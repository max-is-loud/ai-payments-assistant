export default function App() {
  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  return (
    <div className="shell">
      <header className="masthead">
        <h1 className="wordmark">Ledger <small>payments assistant</small></h1>
        <span className="dateline">{today}</span>
      </header>
      <main className="grid">
        <section className="thread" aria-label="Conversation">
          <p className="empty">Ask me to refund, invoice, or summarise.</p>
        </section>
        <aside className="rail" aria-label="Today and escalations" />
      </main>
    </div>
  );
}
