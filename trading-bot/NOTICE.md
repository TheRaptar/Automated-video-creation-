# Credits

Ideas adapted from **Jakeschincariol/day-trader-skill** (MIT License, Copyright (c) 2026 Jake Schincariol):
- `trader-timemachine` -> `algo/montecarlo.py`: replay many alternative histories with a fixed seed and give a plain-language
  verdict against a break-even yardstick. Re-implemented for portfolios (random-picking null test, block bootstrap); no code copied.
- `trader-risk`, `trader-budget` -> `algo/risk_gate.py`: PASS/BLOCK pre-trade checks with reasons, and sizing by maximum loss.
  Re-implemented for Indian delivery trading; no code copied.
- `trader-broker` -> design principle for Phase 3: nothing is sent unless (1) the risk gate passed that exact order,
  (2) you explicitly approved that exact order, (3) the platform asks for confirmation. Not yet implemented.
