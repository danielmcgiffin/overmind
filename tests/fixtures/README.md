# Replay fixtures

No licensed `.SC2Replay` fixture is checked into this repository. A supplied
fixture was not mounted in the build workspace.

For an end-to-end local validation, place a replay at that path or pass any
local `.SC2Replay` path to:

```bash
./sc2review analyze "/path/to/game.SC2Replay" --player "ExactName"
```

The unit tests use small normalized event fixtures so they do not redistribute
Blizzard replay data or hard-code a particular game's conclusions.
