Run: run_20260903_104844.837_10

Experiment:
Two nested `rote play inspect --json` steps were executed in parallel.

Observed:
Both validation steps completed.
Both nested inspect steps failed after ~30 seconds.
Compare was correctly blocked.

Correction:
Serialize the two registry inspections while retaining parallel input validation.
