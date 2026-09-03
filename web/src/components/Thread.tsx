import { findComparison } from "../lib/comparison";
import type { Turn } from "../state/useConversation";
import { AssistantBubble, UserBubble } from "./Bubbles";
import { ComparisonChart } from "./ComparisonChart";
import { ConfirmationCard } from "./ConfirmationCard";
import { ErrorStrip } from "./ErrorStrip";
import { Markdown } from "./Markdown";
import { ReceiptCard } from "./ReceiptCard";
import { Trail } from "./Trail";

interface Actions {
  onApprove: (actionId: string) => void;
  onCancel: (actionId: string) => void;
  onRetry: (text: string) => void;
}

// A failed send is retried with the owner's own words: the user turn just before
// it. A failed approval keeps its confirmation card, whose Approve button is the
// retry; re-sending the prompt would only propose the action a second time.
function retryFor(turns: Turn[], index: number, onRetry: Actions["onRetry"]): (() => void) | undefined {
  if (turns[index].confirmation) return undefined;
  const previous = turns[index - 1];
  const text = previous?.role === "user" ? previous.text : undefined;
  return text ? () => onRetry(text) : undefined;
}

function AssistantTurn({ turn, busy, onApprove, onCancel, retry }: {
  turn: Turn;
  busy: boolean;
  onApprove: Actions["onApprove"];
  onCancel: Actions["onCancel"];
  retry?: () => void;
}) {
  const confirmation = turn.confirmation;
  const comparison = findComparison(turn.events);
  return (
    <div className="ldg-turn">
      <Trail events={turn.events} />
      {confirmation && (
        <ConfirmationCard
          confirmation={confirmation} decided={turn.decided} busy={busy}
          onApprove={() => onApprove(confirmation.action_id)} onCancel={() => onCancel(confirmation.action_id)}
        />
      )}
      {turn.result && <ReceiptCard result={turn.result} />}
      {turn.text && (
        <AssistantBubble>
          {comparison && <ComparisonChart comparison={comparison} />}
          <Markdown>{turn.text}</Markdown>
        </AssistantBubble>
      )}
      {turn.error && <ErrorStrip onRetry={retry}>{turn.error}</ErrorStrip>}
    </div>
  );
}

export function Thread({ turns, busy, error, onApprove, onCancel, onRetry }: {
  turns: Turn[];
  busy: boolean;
  error: string | null;
} & Actions) {
  return (
    <div className="ldg-thread">
      {turns.length === 0 && <p className="ldg-empty">Ask me to refund, invoice, compare, or summarise.</p>}
      {turns.map((turn, i) =>
        turn.role === "user" ? (
          <UserBubble key={turn.id}>{turn.text}</UserBubble>
        ) : (
          <AssistantTurn
            key={turn.id} turn={turn} busy={busy} onApprove={onApprove} onCancel={onCancel}
            retry={retryFor(turns, i, onRetry)}
          />
        ),
      )}
      {error && <ErrorStrip>{error}</ErrorStrip>}
    </div>
  );
}
