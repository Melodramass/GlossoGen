import type { DisplayEntry } from "./display-entry";

interface Turn {
  agentId: string;
  timestamp: string;
  index: number;
  displayName?: string;
}

export type ChatRow =
  | { kind: "round-start" | "round-end"; key: string; roundNumber: number }
  | {
      kind: "entry";
      key: string;
      roundNumber: number;
      turn: Turn;
      isTurnStart: boolean;
      entry: DisplayEntry;
    };

/** Build measured rows and navigation indexes in one pass. Entries share only
 * their turn's header metadata; no intermediate round/turn entry arrays. */
export function buildChatRows(messages: DisplayEntry[]) {
  const rows: ChatRow[] = [];
  const rowIndexByRound = new Map<number, number>();
  const rowIndexByMessage = new Map<string, number>();
  let currentRound: number | undefined;
  let turn: Turn | undefined;

  function addBoundary(kind: "round-start" | "round-end", roundNumber: number) {
    rows.push({ kind, key: `${kind}-${roundNumber}`, roundNumber });
  }

  for (const entry of messages) {
    const roundNumber = entry.round_number;
    if (roundNumber !== currentRound) {
      if (currentRound !== undefined) addBoundary("round-end", currentRound);
      rowIndexByRound.set(roundNumber, rows.length);
      addBoundary("round-start", roundNumber);
      currentRound = roundNumber;
      turn = undefined;
    }
    const isTurnStart = turn?.agentId !== entry.sender_agent_id;
    if (!turn || isTurnStart) {
      turn = {
        agentId: entry.sender_agent_id,
        timestamp: entry.timestamp,
        index: turn ? turn.index + 1 : 0,
      };
    }
    // Later messages in the same turn can supply the historical display name
    // used by its first entry, even when that first entry is reasoning/tool use.
    if (
      !turn.displayName &&
      entry.sender_display_name &&
      entry.sender_display_name !== turn.agentId
    ) {
      turn.displayName = entry.sender_display_name;
    }
    rowIndexByMessage.set(entry.message_id, rows.length);
    rows.push({
      kind: "entry",
      key: `entry-${entry.message_id}`,
      roundNumber,
      turn,
      isTurnStart,
      entry,
    });
  }
  if (currentRound !== undefined) addBoundary("round-end", currentRound);
  return { rows, rowIndexByRound, rowIndexByMessage };
}
