# Review method

The review is designed to identify causal failure cascades, not to produce a leaderboard of imperfections.

## Diagnostic hierarchy

1. **Spending and float:** identify when meaningful unspent resources begin, how large and sustained the episode becomes, and whether the observed state points to supply, production, larva, technology, worker saturation, or an unknown constraint.
2. **Supply and worker reality:** compare the bank to supply room, worker count, base count, and a replay-specific spending checkpoint. A worker count is not a goal by itself; it is useful only in relation to the infrastructure available to convert income.
3. **Production and conversion:** determine what the bank could plausibly become after accounting for gas, supply, larva, tech, and known production structures. Queue state is treated as unavailable unless the replay proves it.
4. **Reinforcement and combat:** inspect combat only when it creates a spending window, requires a replacement wave, or explains why resources remained unconverted. A favorable fight does not outrank a sustained bank merely because it decided the result.
5. **Turning point and consequences:** locate the first major state change that materially changes the player's options. Distinguish the decisive spending/commitment error from later consequences.
6. **Leverage rule:** give one measurable next-game trigger tied to the observed state and a feasible alternative decision.

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

## Spending episodes

Resource float is reported as an episode rather than a list of high snapshots. A candidate episode begins when minerals reach 800 or gas reaches 500 and ends at the first later snapshot below both thresholds. It becomes meaningful when it is sustained for at least 160 loops, reaches at least 1,200 minerals or 800 gas, or otherwise has repeated state evidence. Each episode retains start/end/peak timestamps, worker and base counts, supply, known production structures, observed larva, technology resources, upgrades, fighting overlap, post-fight bank movement, a primary constraint label, and source snapshot references.

The analyzer does not call a bank intentional merely because it is large. It avoids criticizing a named technology or expansion reserve when the corresponding in-progress or completion evidence supports that interpretation. “Production idle” is a candidate when known production exists alongside a large bank; complete queue state and attention are not replay-visible. No `attention_diversion` label is emitted from combat overlap alone.

Unit-equivalent explanations are resource bounds, not simulated purchase orders. The report accounts for gas, supply room, observed larva, required tech, and known production structures, then distinguishes that bounded immediate upper limit from the larger resource-only equivalent.

## Coaching output

The player-facing `review.md` is a compressed 200–400 word coaching output with five default sections: `Spending verdict`, `Float timeline`, `Why the bank accumulated`, `What the bank should have become`, and `Next-game trigger`. It has one primary spending thesis, no more than three supporting findings, and one measurable trigger. Each candidate finding passes a relevance gate: it must materially affect the result, explain the primary diagnosis, or be actionable in at least two of those three dimensions. Every review includes a concise **Macro benchmark/reality** comparison: a replay-specific worker/saturation spending checkpoint versus actual workers, bank, and spending state. Detailed chronology, tables, caveats, methodology, and source references belong in `evidence.md`, not in the coaching review. Combat gets at most one short supporting paragraph unless it is itself the spending diagnosis.
