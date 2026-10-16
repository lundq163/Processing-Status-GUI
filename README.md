# Processing Status GUI

PyQt6 app that tracks BCP sessions through the processing pipeline and lets you filter final BrainSwipes QC results.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python pipeline_tracker.py --participants_tsv all_datasheets/bcp_participants.tsv
python pipeline_tracker.py --participants_tsv all_datasheets/bcp_participants.tsv --data_dir all_datasheets
python pipeline_tracker.py --help
```

| Option | Meaning |
|---|---|
| `--participants_tsv FILE` | BIDS `participants.tsv` with `participant_id` and `session_id` columns; the canonical session list. Required unless `--session` is given. (`--input` still works as an alias.) |
| `--data_dir DIR` | Import every schema-named CSV under DIR at startup (recursive). |
| `--session FILE` | Restore a saved session (see below). |
| `--stages ...` | Limit the pipeline columns. |

`all_datasheets/` holds the sample participants file and example CSVs (every file already follows the naming schema), so the commands above work as is. The tests use it too.

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

The audit-report format `{date}_{output folder}_{nibabies|xcpd}_v{pipeline version}_audit_report.csv` (columns `sub_id`, `ses_id`, `crash_log`, `exec_sum`, `status`) is also recognized as-is, for example `Mar-20_main_folder_xcpd_v0.10.7_audit_report.csv`. Its version is `{output folder}_v{pipeline version}` (`main_folder_v0.10.7`), so each output folder is a selectable version. `success?` is success; a crash log or an `exec_sum` other than `NO_OUTPUTS` with no success is an error; `NO_OUTPUTS` means the session was not run in that folder (pending).

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

## Views and tools

- **Pipeline View** has a filter bar: search by session ID (space/comma separated), current stage, status of the current stage, error-query file, and "has notes". "Showing X of Y" tells you what is visible.
- **Overview / Error Summary** show counts per stage and per error-query file (for the selected versions).
- **Version Comparison** picks a stage and two versions (A, B) and lists sessions whose status differs, labelled `improved` (B succeeded), `regressed`, `changed`, `only_in_a` or `only_in_b`.
- **Summary** is a text report: complete vs. not complete, where incomplete sessions stopped, success/error/pending/no-data per stage and version, sessions not in `participants.tsv` per file. **Save report** writes the `.txt` plus `<name>_incomplete.csv`.
- **Export Current View** writes what the current view shows to CSV (filtered sessions, BrainSwipes selection, version comparison) or saves the summary report. Session exports include the selected version and status of each stage, BrainSwipes result, error files and notes.
- **Import Folder** imports every CSV under a folder that follows the naming schema; others are listed as skipped, with the expected pattern.
- **Save Session / Load Session** store the participants file, the imported CSVs (absolute path, with a path relative to the session file as fallback) and the selected versions as JSON. Loading starts clean and re-imports; missing files are reported and printed as `[WARNING]`.

Imports check columns and give a specific message when a file lacks participant/session ID columns, or (for tracking CSVs) all of `pending`/`success`/`errored`, or (for error CSVs) both `Run_Number` and `Error_Log_Paths`.

## Tests

```bash
pip install -r requirements.txt
pytest tests
```
