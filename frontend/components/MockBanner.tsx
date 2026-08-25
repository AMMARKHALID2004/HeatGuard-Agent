"use client";

import { isMockMode, MOCK_SCENARIOS, type MockScenarioId } from "@/lib/mock";

/**
 * The mock-mode header: an unmissable notice, plus a picker for which sample to play next.
 *
 * The notice is not decoration. Mock decisions are indistinguishable from real ones by design
 * — that is what makes them useful for layout work — which means the only thing preventing a
 * fabricated PROCEED from being read as a measurement during judging is this bar and the
 * `mock-` prefix on the job id. It is deliberately the loudest element on the page.
 *
 * The picker is what makes offline work worth doing: the failure states are the ones you most
 * need to look at and the ones you can least easily provoke against a live backend, since
 * you would have to stall FortyGuard or revoke your own API key to see them.
 *
 * Direction 5: Tactical alert banner at top of briefing panel.
 */
export function MockBanner({
  selected,
  onSelect,
  disabled,
}: {
  selected: MockScenarioId;
  onSelect: (id: MockScenarioId) => void;
  disabled: boolean;
}) {
  // If USE_MOCK_DATA is not explicitly set, don't render anything at all.
  // This ensures production builds never show the mock banner, even if the component
  // is accidentally imported and rendered.
  if (!isMockMode()) return null;

  const decisions = MOCK_SCENARIOS.filter((scenario) => scenario.kind === "decision");
  const failures = MOCK_SCENARIOS.filter((scenario) => scenario.kind === "failure");

  return (
    <section className="card-base border-ember-border bg-ember-surface/30 p-3 animate-fade-in-up">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="rounded bg-ember-500/20 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-widest text-ember-500">
          Mock Data
        </span>
        <p className="caption-text text-text-secondary flex-1 min-w-0">
          Sample responses for layout work. No API is called and no readings are real.
        </p>
        <code className="caption-text font-mono text-ember-500/70 whitespace-nowrap">USE_MOCK_DATA</code>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <ScenarioGroup
          legend="Decisions"
          scenarios={decisions}
          selected={selected}
          onSelect={onSelect}
          disabled={disabled}
        />
        <ScenarioGroup
          legend="Errors"
          scenarios={failures}
          selected={selected}
          onSelect={onSelect}
          disabled={disabled}
        />
      </div>
    </section>
  );
}

function ScenarioGroup({
  legend,
  scenarios,
  selected,
  onSelect,
  disabled,
}: {
  legend: string;
  scenarios: typeof MOCK_SCENARIOS;
  selected: MockScenarioId;
  onSelect: (id: MockScenarioId) => void;
  disabled: boolean;
}) {
  return (
    <fieldset className="flex flex-wrap items-center gap-2" disabled={disabled}>
      <legend className="sr-only">{legend}</legend>
      <span className="caption-text uppercase tracking-widest text-text-muted">{legend}</span>
      {scenarios.map((scenario) => {
        const isSelected = scenario.id === selected;
        return (
          <button
            key={scenario.id}
            type="button"
            onClick={() => onSelect(scenario.id)}
            disabled={disabled}
            aria-pressed={isSelected}
            className={`rounded-md border px-2.5 py-1 caption-text font-medium transition disabled:opacity-40 ${
              isSelected
                ? "border-ember-500/50 bg-ember-surface text-ember-500"
                : "border-border text-text-secondary hover:border-ember-500/50 hover:text-text"
            }`}
          >
            {scenario.label}
          </button>
        );
      })}
    </fieldset>
  );
}