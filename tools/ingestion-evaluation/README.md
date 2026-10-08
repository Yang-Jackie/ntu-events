# Ingestion evaluation

Compare model outputs against frozen Telegram evidence and approved reference
answers. This development tool uses backend validation and canonicalization;
production workers do not import it. Dependencies and tests use the root Python
configuration. Run commands from the repository root.

## Inspect existing results offline

Replace `<run>` with a directory under `var/evaluations/ingestion/`:

```powershell
docker compose run --rm --no-deps backend python -m ntu_events_evaluation.scoring --results var/evaluations/ingestion/<run>/progress.json --references var/evaluations/ingestion/<run>/reference_answers.json
```

Scoring verifies the approved references and dataset linkage without calling a
provider or connecting to the database. `analyze` and `paired` accept
`--run-dir` and write derived reports inside that directory. Paired comparisons
require completed observations for the same cases, with two repetitions.

## Prepare a new experiment

1. Choose an empty run directory. Freeze evidence from an idle source database:

   ```powershell
   docker compose run --rm backend python -m ntu_events_evaluation.prepare --run-dir var/evaluations/ingestion/<new-run> --request-id <id> --source <id> --source-database ntu_events
   ```

   Repeat `--source` for each selected source. The command takes a read-only
   database snapshot, records fingerprints, and drafts references. Optional
   challenge candidates must belong to the selected request. Existing run
   artifacts are never overwritten by preparation.

2. Review reference answers against source evidence. Each case must be READY,
   and the manifest must be APPROVED and bound to the frozen dataset. Create the
   benchmark policy JSON named by `benchmark_policy_file` in the manifest; its
   `addendum` field supplies experiment instructions. These instructions apply
   only to the benchmark.

3. Prepare a separate disposable copy of the source database named
   `ntu_events_eval_<name>`. This tool does not create or clone databases. Keep
   the frozen IDs and event snapshots intact. Use a Compose environment override
   to select that copy; the commands verify both the requested and actual names:

   ```powershell
   docker compose run --rm -e POSTGRES_DB=ntu_events_eval_<name> backend python -m ntu_events_evaluation.replay --run-dir var/evaluations/ingestion/<new-run> --database ntu_events_eval_<name>
   docker compose run --rm -e POSTGRES_DB=ntu_events_eval_<name> backend python -m ntu_events_evaluation.run --run-dir var/evaluations/ingestion/<new-run> --database ntu_events_eval_<name> --budget-usd 2
   ```

   Replay smoke checks roll back application changes and compare fingerprints.
   The runner validates frozen inputs and prints a preflight summary by default.
   Add `--execute` only for an owner-approved paid run. It refuses an existing
   progress file; use a new run for a new experiment.

The current runner compares Luna 6 and Luna 5.6 at low and medium effort with two
repetitions. Its serial budget ledger reserves maximum output and possible HTTP
attempts before each request. Recheck the dated price table and model availability
before future paid runs. Source evidence, provider responses, references, and
reports stay ignored under `var/evaluations/`; credentials stay in `.env`.

See the [development guide](../../docs/DEVELOPMENT.md#offline-ingestion-evaluation-summaries)
for grading limits and cost assumptions. Original scripts retained in a run's
`code_snapshot/` document its provenance; use this maintained package for commands.
