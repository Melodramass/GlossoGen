"use client";

import { X } from "lucide-react";
import { Modal } from "@/shared/components/ui/modal";
import { ProseMarkdown } from "./prose-markdown";

export function ScenarioDescriptionModal({
  scenarioName,
  description,
  onClose,
}: {
  scenarioName: string;
  description: string;
  onClose: () => void;
}) {
  return (
    <Modal
      label={scenarioName}
      width="5xl"
      panelClassName="flex flex-col overflow-hidden"
      panelId={null}
      onClose={onClose}
    >
      <div className="flex items-center justify-between border-b border-border px-5 py-2.5">
        <span className="text-sm font-medium">{scenarioName}</span>
        <button
          aria-label="Close"
          className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="overflow-y-auto px-5 py-3" style={{ maxHeight: "calc(100vh - 6rem)" }}>
        <ProseMarkdown>{description}</ProseMarkdown>
      </div>
    </Modal>
  );
}
