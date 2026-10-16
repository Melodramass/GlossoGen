import { Check, X } from "lucide-react";
import type { components } from "@/types/api.gen";
import { humanize } from "./format";

type RoundResult = components["schemas"]["RoundResult"];

/** The team id a round-detail panel files a single-team result under, whose `team_id` is null. */
export const SOLO_TEAM_ID = "solo";

/** The team id a round result belongs to, with a single-team result under `SOLO_TEAM_ID`. */
export function resultTeamId(result: RoundResult): string {
  if (result.team_id === null) return SOLO_TEAM_ID;
  return result.team_id;
}

/** "Team A" for `team_a`, and plain "Team" for a single team. */
export function teamDisplayName(teamId: string): string {
  if (teamId === SOLO_TEAM_ID) return "Team";
  return humanize(teamId);
}

/** A team's round outcome as a pass/fail pill carrying the scenario's own reason text. */
export function TeamResultPill({ result }: { result: RoundResult | null }) {
  if (result === null) {
    return <span className="text-[11px] text-muted-foreground">no result recorded</span>;
  }
  const tone = result.success
    ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
    : "bg-rose-500/15 text-rose-700 dark:text-rose-400";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${tone}`}
    >
      {result.success ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
      {result.reason}
    </span>
  );
}
