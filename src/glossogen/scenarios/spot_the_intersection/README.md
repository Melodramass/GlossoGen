# spot_the_intersection

Finding the common object across private boards. Each team has `team_size`
viewers, and each viewer holds a board of objects: a shape and a color in one
cell of a grid whose cells every board names the same way (`C4`). Exactly one
object is on every board of a team. The others are on some boards but not all,
so the viewers talk on their team's link channel until they can tell which one
they all hold, and then every member submits it.

`team_size` sets the viewers per team, from 2 to 12. With `near_misses` on (the
default), certification requires that leaving out any one board leaves at least
two candidates, so every viewer is needed to find the answer.

## Task and scoring

- A viewer calls `submit_object(shape, color, cell)` once per round. A
  submission cannot be changed, and the tool never says whether it was right.
- A team is correct only when **every** member submitted the common object. A
  member who never submits, or who names anything else, loses the round for the
  team. Scoring is deterministic; there is no judge.
- Two teams (the default) play the same boards seat for seat on isolated links.
  Among correct teams, the one that sent the fewest link characters wins, and
  ties are shared. Each round's result is announced at the start of the next.
- Characters stop counting once a team's last member submits.
  `round_time_budget_seconds` is an optional hard cap (`-1`, the default, is
  none).

## How a round is built

Each round is planted in this order, from a random stream keyed by the seed and
the round number:

1. **The answer**, on every board.
2. **Near-misses** (with `near_misses` on and three or more viewers): one per
   viewer, on every board except that viewer's. The board missing it holds a
   *stand-in* in the same cell, differing in one attribute. Without any one
   viewer, at least two candidates remain.
3. **Cell twins**: two cells every board fills, one with the shape the same on
   all boards and one with the color the same, never the whole object.
4. **Look twins**: two shape-and-color pairs every board holds, not all in one
   cell. They are drawn from every look, the answer's included.
5. **Decoys** (`decoy_count_*`): objects on more than one board and fewer than
   all.
6. **Fillers** (`filler_count_*`): objects on one board, until every board holds
   the same number.

No placement repeats an object another board already holds in that cell, so
each object is held by exactly the boards it was planted on. Each board's lines
are then shuffled from a separate random stream, so the answer's position in the
list is independent of the board's contents.

Cell and look twins exist so that comparing only part of an object never
isolates the answer: cells alone, shape and color alone, shape with cell, and
color with cell each leave at least two values every board holds.

## Certification

spot_the_difference checked its scenes on exact coordinates, while its viewers
saw only coarse regions. In one round, a removal and a move into the same region
read to the viewers as a single change. That round was played in 56 runs; teams
solved 17 of 112 team-rounds on it (15%) against 1778 of 2022 on every other round
(88%). The checks below run on what the viewers read.

- **Certified from the lines the viewers read.** `board_certification.py` parses
  the rendered lines back and checks the properties above, plus that the declared
  objects are exactly the objects on the boards. It never reads the generator's
  objects. A round that fails is redrawn; one that never passes raises
  `BoardGenerationError` and the run does not start.
- **The certifier is tested by breaking rounds.** `test_board_certification.py`
  takes certified rounds and breaks one property at a time (a second common
  object, a board that rules nothing out, a declaration that does not match, an
  unreadable line) and requires the certifier to name it.
- **No single-board guesser beats chance.** `single_board_guessers.py` runs
  guessers that see one board alone: first listed, last listed, rarest look, most
  common look, most common color, most common shape, nearest the centre, and most
  crowded row. It flags one that beats chance by more than four standard errors,
  clustered by round. Other ways of exploiting a board are not tested. During
  development it flagged the answer listed first on every board, and a look twin
  that excluded the answer's look and so made that look rarer than others.

### Before a cohort

Sweep every preset at every team size:

```bash
VIRTUAL_ENV= uv run --no-sync python -m \
  glossogen.scenarios.spot_the_intersection.scripts.certify_boards --seed-count 200
```

It exits non-zero if any round fails to generate or re-certify, or any
single-board guess beats chance.

### After the first runs

Audit what the viewers were actually sent, from each run's event log:

```bash
VIRTUAL_ENV= uv run --no-sync python -m \
  glossogen.scenarios.spot_the_intersection.scripts.audit_recorded_boards \
  runs/spot_the_intersection/<run_id> [...]
```

It requires every viewer's injected board to match the board recorded for its
seat, both teams to have been sent the same boards, and the boards as sent to
certify. It also notes rounds whose recorded boards differ from what the current
checkout generates, which happens when generation changed between two cohorts
sharing a seed.

Then compare round success round by round. Runs sharing a seed and board knobs
play identical boards (generation is keyed by seed and round number), so a round
whose mean `round_success` sits far below the others is a candidate for a bad
board. On spot_the_difference's runs, this table shows its bad round at 0.33
against 0.6 to 1.0 for the rest:

```bash
glossogen analyze --runs-dir ./runs --scenario spot_the_intersection --label <cohort> \
  --grain round --group-by round_number \
  --measure round_success_team_a:mean --measure round_success_team_b:mean
```

## What viewers are told

The system prompt states the grid and its cell names, that exactly one object is
on every board, the submission rule, and the competition. It does not mention
near-misses, twins, decoys, or that every board is needed. Each round's briefing
lists the viewer's own board and the previous round's result, never the answer.

## Modes

- `two_teams: true` (`knobs_default.json`): two teams on isolated `link_a` /
  `link_b`, competing on the same boards.
- `two_teams: false` (`knobs_single_team.json`): one team on `link`; the
  character count is the score.

## Key knobs

- `team_size`: viewers per team, 2 to 12.
- `grid_size`: the grid needs at least twice as many cells as the largest board.
- `near_misses`: whether every board is required. Off, some viewers may be left
  out of a round without loss.
- `decoy_count_values` / `_weights` and `filler_count_values` / `_weights`: drawn
  per round. A board holds the planted objects (the team size plus five, with
  near-misses on) plus both counts. Decoys need three viewers, so set
  `decoy_count_values: [0]` for `team_size: 2`.
- `round_time_budget_seconds`, `channel_noise_level`, `noise_replacement_mode`,
  and the postmortem knobs, as in other scenarios.

## Recorded events

- `spot_the_intersection_round_started`: every board as read, every object with
  its kind and the seats holding it, the answer, and the certificate: candidates
  left without each seat, the partial-comparison counts, the generation attempts,
  and two reference costs in object mentions (every board listed in full, and
  each viewer in turn listing what survives on its board).
- `intersection_submission_recorded`: each submission, whether it was the answer,
  and the team's character count at that moment.

## Metrics

All generic: `round_success` (`_team_a` / `_team_b` with two teams),
`round_success_after_resume`, the per-team character and language metrics on
each team's link, `communication_*` via `build_communication_rounds`, and the
`protocol_*` family via `get_protocol_probe_config` /
`get_protocol_explanation_config`.

## Files

- `board_model.py`, `board_rendering.py`: objects, cell names, and the line
  format with its exact inverse.
- `board_generation.py`, `board_certification.py`: planting and certification.
- `single_board_guessers.py`: the single-board leak check.
- `recorded_board_audit.py`, `scripts/audit_recorded_boards.py`: the recorded-run
  audit.
- `scripts/certify_boards.py`: the sweep before a cohort.
- `world.py`, `world_state.py`, `outcome_reconstruction.py`: character metering,
  submissions and locking, scoring, and rebuilding outcomes on resume from the
  recorded answers.
- `tools.py`, `team_declaration.py`, `seats.py`, `injection_rendering.py`,
  `round_event_conversion.py`, `events.py`: the tool, roster, prompts, and events.
