# Processing Status GUI

PyQt6 app that tracks BCP sessions through the processing pipeline and lets you filter final BrainSwipes QC results.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python pipeline_tracker.py --input data_that_work/bcp_participants.tsv
```

`--input` is a BIDS `participants.tsv` with `participant_id` and `session_id` columns; it is the canonical session list. Optional `--stages` limits the pipeline columns.

## CSV naming schema

Every CSV you import should be named:

```text
{stage}__{version}__{audit|errors}[__label].csv
```

- `stage`: `mriqc`, `bibsnet`, `nibabies`, `xcpd`, `brainswipes`, or `notes`
- `version`: free text identifying the pipeline run, with no double underscores (for example `25.0.1`, `anat_only`, `0.10.7`). Ignored for `brainswipes` and `notes`, but still required.
- `audit` or `errors`: audit/tracking output, or error-query output (pipeline stages only)
- `label`: optional; use it to tell apart several files of the same kind (for example the error category)

Examples:

```text
mriqc__v1__audit__counts.csv
bibsnet__v1__audit.csv
nibabies__25.0.1__audit.csv
nibabies__anat_only__errors__node_execution.csv
xcpd__0.10.7__errors__no_low_motion_runs.csv
brainswipes__30July__audit.csv
notes__unfindable__audit.csv
```

Files that do not match prompt for stage, version, and type when imported. Several files can be selected at once.

## Versions

Import audit and error CSVs for as many versions of a stage as you like. Each stage with imported versions gets a version picker at the top of the window. The selected version of each stage drives the pipeline view, overview, error summary, and counts; switching versions recomputes everything. Session details show every version's data and errors.

## Tracking rules

- A session advances through MRIQC, BIBSNet, NiBabies and XCP-D in order and stops at the first stage that is not successful (for the selected versions). Import order does not matter.
- A session is **Complete** when XCP-D succeeds.
- BrainSwipes data does not move sessions; use it as a filter.
- Error CSVs mark that version of the stage as errored. A later success audit for the same version clears its errors.
- BIBSNet segmentations are QC'd manually, so BIBSNet status comes from the tracking CSV rather than an automated audit.

## Input formats

| Source | Contents |
|---|---|
| mriqc | best anatomical, anatomical counts, QC sheet, or series-run key (detected from columns); counts mark MRIQC successful |
| bibsnet, nibabies, xcpd | `participant_id`, `session_id`, `pending`, `success`, `errored` |
| errors | `Subject_IDs`, `Session_IDs`, `Run_Number`, `Error_Log_Paths` |
| brainswipes | results sheet (`subject`, `session`, `recon`, `overall`, scores) and/or passable-subjects list; merged by recon; a session passes if any recon passes |
| notes | `participant_id`, `session_id`, `notes` |

Sessions that appear in an imported file but not in `participants.tsv` are skipped. They are listed in the import summary and printed to the terminal as `[WARNING]`.

## BrainSwipes view

Filter by recon, overall result, XCP-D success, and thresholds on any score column (averages and pass counts are minimums, fail counts are maximums). **Export Matching Sessions** writes the filtered rows to CSV.

## Tests

```bash
pip install pytest
pytest tests
```
