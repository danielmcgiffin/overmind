# Review method

The review is designed to identify causal failure cascades, not to produce a leaderboard of imperfections.

## Diagnostic hierarchy

1. **Outcome and state:** identify the result, participants, duration, and the largest observable state changes.
2. **Turning point:** locate the first major state change that materially changes the player's options. This may be a negative engagement loss, but it can also be a favorable removal of the opponent's expensive core that creates the winning conversion window.
3. **Preconditions:** inspect earlier harassment, worker/supply/resource state, production capacity, expansion/upgrade timing, and army composition.
4. **Decision categories:** classify supported issues as strategic commitment, build/tech, economy/worker production, scouting/information, tactical engagement, reinforcement/disengagement, or mechanical execution.
5. **Consequences:** identify later losses that follow from the turning point. Do not call every later event a new root cause.
6. **Leverage rule:** give one or two concrete rules tied to a timestamp and an alternative decision.

## Facts versus inferences

Factual statement:

> At 7:09 real time, `UnitDied` events recorded 12 deaths near map position `[44, 61]`, including 8 units owned by the reviewed player.

Inference:

> This is a candidate tactical turning point because the local tracked losses were substantially worse and the nearest post-fight army snapshot fell.

The first statement is a normalized replay observation with evidence IDs. The second is a diagnostic conclusion and must cite the first statement's evidence. The report labels these as `FACT` and `INFERENCE` and keeps them in separate JSON arrays.

Never invent vision, intent, camera attention, control-group use, player thought processes, or a precise movement path. Use “observed,” “supports,” “candidate,” and “consistent with” when the replay cannot prove a stronger claim. Use “unavailable” when the stream does not contain the needed evidence.

## Turning-point rules

- Prefer the largest negative state change that affects future options, not the earliest imperfection.
- A candidate fight must be spatially and temporally clustered. Total deaths per minute cannot define a fight.
- Compare pre-fight and post-fight snapshots where available: worker count, supply, active-force value, resources, and composition.
- Treat a fight as more decisive when the player's local losses materially exceed the opposing local losses and the post-fight state remains behind.
- Do not call a fight a loss from unit-count asymmetry alone. If killer attribution shows cheap units died while tanks or another expensive core were removed, classify it as a favorable or at least non-negative trade and carry that advantage into the next conversion question.
- Classify small-force harassment separately from army fights. A few units that kill workers or a production/supply structure can be a favorable tempo trade even when those units die afterward. Worker pull time is only claimed when movement evidence supports it; player-provided visual confirmation may be noted separately from replay-native facts.
- For a winning game, report the strongest favorable transition separately from a decisive mistake. A win should not be forced to contain a tactical error merely because the player lost units.
- If the player recovers after an event, label it a setback rather than the decisive loss.
- If evidence is sparse or a fight cannot be spatially localized, say so instead of filling the gap with generic advice.

## Decisive mistake versus later consequence

The decisive mistake is the earliest decision or commitment that changes the game from recoverable to materially constrained under the observed state. It is not automatically:

- the first worker loss,
- the first missed production cycle,
- the first upgrade delay,
- or the first fight that went badly.

For example, worker harassment is opponent-created damage. The player may still have a coherent response. If the later response is to stop workers, over-commit to army, and attack into an already-defended position, the report should distinguish the harassment (precondition), the response (possible strategic/economic inference), and the attack loss (candidate turning point). Reinforcements entering the same losing fight are usually consequences unless evidence shows that the reinforcement decision independently changed the state.

## Classification guidance

- **Strategic commitment:** the observable economy/tech/army state supports an all-in, expansion, or defensive commitment whose tradeoff fails.
- **Build or tech:** expansion/tech/upgrade timing is materially different and the alternative is tied to a reachable state, not a build-order fantasy.
- **Economy/worker production:** use worker counts, worker deaths, resource rates, supply, and explicit production evidence. Do not call a plateau an error automatically.
- **Scouting/information:** only claim what replay events support. A missing scout event is not proof the player did not look.
- **Tactical engagement:** spatial loss cluster, composition/value state, target position, and retreat/commitment evidence when available.
- **Reinforcement/disengagement:** units appear near a losing fight after it begins; call this approximate when based on sparse positions.
- **Mechanical execution:** only claim a mechanical issue when command/ability events provide evidence. Do not infer camera or control-group errors from a bad outcome.
- **Opponent-created damage:** killer attribution or ownership/loss evidence points to damage caused by the opponent.
- **Self-inflicted damage:** the player's own observable commitment or state change is supported; label the conclusion as inference.

## Coaching output

The player-facing `review.md` is a compressed 250–500 word coaching output with no more than four conditional sections: `Verdict`, `Decisive sequence`, `What mattered`, and `Next-game rules`. It has one primary thesis, one decisive sequence, no more than three supporting findings, and no more than two rules. Each candidate finding passes a relevance gate: it must materially affect the result, explain the primary diagnosis, or be actionable in at least two of those three dimensions. The detailed timeline, tables, caveats, methodology, and source references belong in `evidence.md`, not in the coaching review. Advice must include an exact real elapsed timestamp, the observed state change, and a feasible alternative. “Macro better,” “make more workers,” and “take better fights” are not acceptable without that evidence.
