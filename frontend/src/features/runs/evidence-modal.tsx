"use client";

import { X } from "lucide-react";
import { Modal } from "@/shared/components/ui/modal";
import type { components } from "@/types/api.gen";
import { humanize } from "./format";
import { ProseMarkdown } from "./prose-markdown";

type MeasurementResponse = components["schemas"]["MeasurementResponse"];

export function EvidenceModal({
  measurement,
  onClose,
}: {
  measurement: MeasurementResponse;
  onClose: () => void;
}) {
  return (
    <Modal
      label={humanize(measurement.metric_name)}
      width="2xl"
      panelClassName="flex max-h-[80vh] flex-col overflow-hidden"
      panelId={null}
      onClose={onClose}
    >
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{humanize(measurement.metric_name)}</span>
          <span className="text-xs text-muted-foreground">
            {measurement.score.toFixed(2)} {measurement.score_unit}
          </span>
        </div>
        <button
          aria-label="Close"
          className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="mb-3 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Summary
        </div>
        <ProseMarkdown>{measurement.summary}</ProseMarkdown>

        {measurement.per_round.length > 0 ? (
          <>
            <div className="mb-2 mt-5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Per round
            </div>
            <div className="divide-y divide-border">
              {measurement.per_round.map(observation => (
                <div
                  key={observation.round_number}
                  className="flex flex-col gap-0.5 py-1.5 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">Round {observation.round_number}</span>
                    <span className="text-muted-foreground">{observation.value.toFixed(2)}</span>
                  </div>
                  {observation.note ? <ProseMarkdown>{observation.note}</ProseMarkdown> : null}
                </div>
              ))}
            </div>
          </>
        ) : null}

        {measurement.per_agent.length > 0 ? (
          <>
            <div className="mb-2 mt-5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Per agent
            </div>
            <div className="divide-y divide-border">
              {measurement.per_agent.map(observation => (
                <div key={observation.agent_id} className="flex flex-col gap-0.5 py-1.5 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{humanize(observation.agent_id)}</span>
                    <span className="text-muted-foreground">{observation.value.toFixed(2)}</span>
                  </div>
                  {observation.note ? <ProseMarkdown>{observation.note}</ProseMarkdown> : null}
                </div>
              ))}
            </div>
          </>
        ) : null}
      </div>
    </Modal>
  );
}
