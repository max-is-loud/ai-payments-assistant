import type { DailyFacts, Escalation, SeriesResponse } from "../../api/types";
import type { EscalationState } from "../../state/useDashboard";
import { ErrorStrip } from "../ErrorStrip";
import { EscalationCard } from "./EscalationCard";
import { HourlySection } from "./HourlySection";
import { RailSection } from "./RailSection";
import { TopCustomersSection } from "./TopCustomersSection";
import { UnpaidSection } from "./UnpaidSection";

// Borderless sections, then one amber card per pending escalation. With nothing
// pending, a quiet section says where escalations will appear so the loop is discoverable.
export function Rail({ facts, series, escalations, escalationState, onApprove, error }: {
  facts: DailyFacts | null;
  series: SeriesResponse | null;
  escalations: Escalation[];
  escalationState: Record<string, EscalationState>;
  onApprove: (id: string) => void;
  error: string | null;
}) {
  return (
    <aside className="ldg-rail" aria-label="Today and escalations">
      <HourlySection hourly={series?.hourly_today ?? null} />
      <TopCustomersSection customers={series?.top_customers ?? null} />
      <UnpaidSection facts={facts} />
      {error && <ErrorStrip>{error}</ErrorStrip>}
      {escalations.length === 0 ? (
        <RailSection title="Escalations">
          <p className="ldg-empty">Nothing waiting. A customer payment at or above the bot's limit will appear here.</p>
        </RailSection>
      ) : (
        escalations.map((escalation) => (
          <EscalationCard
            key={escalation.id}
            escalation={escalation}
            state={escalationState[escalation.id] ?? "pending"}
            onApprove={() => onApprove(escalation.id)}
          />
        ))
      )}
    </aside>
  );
}
