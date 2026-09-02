import { Button } from "./Button";

// Coral left-rule strip: one sentence and, when possible, a way out. Developer
// detail only ever arrives when the API runs with DEBUG=1 (describeError puts
// it after a newline); it is shown as a mono line rather than run into the sentence.
export function ErrorStrip({ children, onRetry }: { children: string; onRetry?: () => void }) {
  const [sentence, ...rest] = children.split("\n");
  const detail = rest.join("\n").trim();
  return (
    <div className="ldg-error" role="alert">
      <span>
        {sentence}
        {detail && <span className="detail">{detail}</span>}
      </span>
      {onRetry && <Button variant="danger" onClick={onRetry}>Retry</Button>}
    </div>
  );
}
