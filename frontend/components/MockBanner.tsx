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
    <div className="rounded-lg border border-amber-400/40 bg-amber-400/10 px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="rounded bg-amber-400/20 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-widest text-amber-200">
          Mock data
        </span>
        <p className="text-sm text-amber-100/90">
          Sample responses for layout work. No API is called and no readings are real.
        </p>
        <code className="text-xs text-amber-200/60">USE_MOCK_DATA</code>
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
    </div>
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
      <span className="text-[11px] uppercase tracking-widest text-amber-200/50">{legend}</span>
      {scenarios.map((scenario) => {
        const isSelected = scenario.id === selected;
        return (
          <button
            key={scenario.id}
            type="button"
            onClick={() => onSelect(scenario.id)}
            disabled={disabled}
            // `aria-pressed` rather than a radio group: these are toggle buttons that also
            // read out their state, and the visual selection is the only affordance.
            aria-pressed={isSelected}
            className={`rounded-md border px-2.5 py-1 text-xs font-medium transition disabled:opacity-40 ${
              isSelected
                ? "border-amber-300/70 bg-amber-300/20 text-amber-100"
                : "border-amber-400/25 text-amber-200/70 hover:border-amber-300/50 hover:text-amber-100"
            }`}
          >
            {scenario.label}
          </button>
        );
      })}
    </fieldset>
  );
}
