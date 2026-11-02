# Sample plan: a two-storey house (plan 2)

Two floor plans to try Plan2Cost with: `ground.png` and `first.png` (scale 1:100, images with no text layer).
The title block is blanked: no architect, client, address or project name. Shared with permission, for testing only.

Inputs used in the demo: storey height 3.0 m, hip roof, standard finish.

```bash
python -m plan2cost.agent --floor ground=samples/plan2/ground.png --floor first=samples/plan2/first.png --storey-height 3.0 --roof hip
```

Or in the console (`python ui/server.py`, then http://localhost:8765): New estimate, add both floors, 3.0 m, hip roof.
A run takes about 5 minutes. On Nov 2, 2026 it gave walls of 115.6 m (ground) and 121.3 m (first) and an estimate of about 84.8M to 85.0M naira (range 73M to 109M);
wall girth against the surveyor's own totals for this plan: ground 107.1 m, first 127.6 m.
