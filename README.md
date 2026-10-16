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
{date}_{output_folder}_{tool}_v{version}_{audit|error}_report[_{label}].csv
{date}_{description}_{brainswipes|notes}_report.csv
```

- `date`: one token without underscores that contains a digit, for example `Mar-20` or `2026-03-20`
- `output_folder`: the processing output folder the audit covers (`main_folder`, `reproc-mfc`, `mcribs-4to8`, `infantfs_gt24mo`, ...). Underscores are allowed.
- `tool`: `mriqc`, `bibsnet`, `nibabies` or `xcpd`
- `version`: the pipeline version after a literal `v` (`v25.0.1`, `v0.10.7`); no underscores
- `audit` or `error`: audit/tracking output, or error-query output (pipeline tools only)
- `label`: optional; tells apart several files of the same kind (the MRIQC table type, the error category)
- `description` (brainswipes, notes): free text such as `results` or `passable`; these are not tied to a pipeline version

The **version** shown in the GUI is `{output_folder}_v{version}` (for example `main_folder_v0.10.7`). Audit and error files with the same output folder and version overlay each other, and each output folder is its own selectable version.

Examples:

```text
Mar-20_main_folder_nibabies_v25.0.1_audit_report.csv
Mar-20_reproc-mfc_xcpd_v0.10.7_audit_report.csv
Mar-20_main_folder_nibabies_v25.0.1_error_report_node_execution.csv
Oct-15_pilot_mriqc_v1_audit_report_anat_counts.csv
Jul-30_results_brainswipes_report.csv
Oct-15_unfindable_notes_report.csv
```

Audit-report columns are `sub_id`, `ses_id`, `crash_log`, `exec_sum`, `status` (the older `participant_id`/`session_id`/`pending`/`success`/`errored` columns still work). `success?` is success; a crash log or an `exec_sum` other than `NO_OUTPUTS` with no success is an error; `NO_OUTPUTS` means the session was not run in that folder (pending).

Files that do not match prompt for stage, version, and type when imported (with Import Folder they are skipped and listed). Several files can be selected at once.

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
