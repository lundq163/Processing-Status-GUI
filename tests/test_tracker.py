import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from PyQt6.QtWidgets import QApplication

import pipeline_tracker as pt

DATA = ROOT / "all_datasheets"
SAMPLES = DATA
BS_RESULTS = SAMPLES / "Jul-30_results_brainswipes_report.csv"
BS_PASSABLE = SAMPLES / "Jul-30_passable_brainswipes_report.csv"
XCPD_ERRORS = SAMPLES / "Oct-15_main_folder_xcpd_v0.10.7_error_report_no_low_motion_runs.csv"


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(app, tmp_path):
    w = pt.PipelineTrackerWindow(str(DATA / "bcp_participants.tsv"), None)
    for name in ["Oct-15_pilot_mriqc_v1_audit_report_best_anatomical.csv", "Oct-15_pilot_mriqc_v1_audit_report_anat_counts.csv",
                 "Oct-15_pilot_bibsnet_v3.4.1_audit_report.csv", "Mar-20_main_folder_nibabies_v25.0.1_audit_report.csv", "Mar-20_main_folder_xcpd_v0.10.7_audit_report.csv"]:
        w.import_file(str(DATA / name))
    w.tmp_path = tmp_path
    return w


def stage_counts(w):
    from collections import Counter
    return Counter(s.current_stage for s in w.sessions.values())


def test_parse_filename():
    spec = pt.parse_csv_filename("x/Mar-20_main_folder_nibabies_v25.0.1_audit_report.csv")
    assert spec == {"stage": "Nibabies", "version": "main_folder_v25.0.1", "kind": "audit",
                    "label": "", "date": "Mar-20", "folder": "main_folder"}
    spec = pt.parse_csv_filename("Mar-20_reproc-mfc_xcpd_v0.10.7_error_report_no_low_motion.csv")
    assert (spec["kind"], spec["label"], spec["version"]) == ("errors", "no_low_motion", "reproc-mfc_v0.10.7")
    spec = pt.parse_csv_filename("Jul-30_results_brainswipes_report.csv")
    assert spec["stage"] == "BrainSwipes QC" and spec["version"] == pt.PipelineConfig.UNVERSIONED
    assert pt.parse_csv_filename("Oct-15_x_notes_report.csv")["stage"] == "Notes"
    # old schema and malformed names are rejected
    for bad in ("nibabies__25.0.1__audit.csv", "nibabies_tracking.csv",
                "Mar-20_main_folder_foo_v1_audit_report.csv",
                "main_folder_nibabies_v1_audit_report.csv",
                "Mar-20_main_folder_nibabies_audit_report.csv",
                "Mar-20_x_brainswipes_error_report.csv"):
        assert pt.parse_csv_filename(bad) is None, bad


def test_import_requires_schema_name(window):
    with pytest.raises(ValueError):
        window.import_file(str(DATA / "bcp_participants.tsv"))


def test_xcp_d_success_is_complete(window):
    complete = [s for s in window.sessions.values() if s.current_stage == "Complete"]
    assert complete
    assert all(s.stage_status["XCP-D"] == "success" for s in complete)
    assert stage_counts(window)["XCP-D"] > 0


def test_import_order_does_not_matter(app, tmp_path):
    w = pt.PipelineTrackerWindow(str(DATA / "bcp_participants.tsv"), None)
    for name in ["Mar-20_main_folder_xcpd_v0.10.7_audit_report.csv", "Mar-20_main_folder_nibabies_v25.0.1_audit_report.csv",
                 "Oct-15_pilot_bibsnet_v3.4.1_audit_report.csv", "Oct-15_pilot_mriqc_v1_audit_report_anat_counts.csv"]:
        w.import_file(str(DATA / name))
    assert stage_counts(w)["Complete"] > 0


def test_version_toggle_changes_tracking(window):
    before = stage_counts(window)
    failing = window.tmp_path / "Oct-15_new_xcpd_v0.11.0_audit_report.csv"
    failing.write_text("participant_id,session_id,pending,success,errored\n" + "\n".join(
        f"{pid},{sid},FALSE,FALSE,TRUE" for pid, sid in window.sessions) + "\n")
    window.import_file(str(failing))
    assert window.versions("XCP-D") == ["main_folder_v0.10.7", "new_v0.11.0"]
    assert stage_counts(window) == before  # first imported version stays selected

    window.active_versions["XCP-D"] = "new_v0.11.0"
    window.recompute()
    after = stage_counts(window)
    assert after["Complete"] == 0
    assert after["XCP-D"] == before["Complete"] + before["XCP-D"]

    window.active_versions["XCP-D"] = "main_folder_v0.10.7"
    window.recompute()
    assert stage_counts(window) == before


def test_all_views_render(window):
    window.import_file(str(BS_RESULTS))
    window.rebuild_version_controls()
    for view in (window.show_pipeline_view, window.show_overview,
                 window.show_error_summary, window.show_brainswipes_view):
        view()
    pt.SessionDetailDialog(next(iter(window.sessions.values())))


def test_brainswipes_filters(window):
    window.import_file(str(BS_RESULTS))
    base = pt.filter_brainswipes(window.sessions)
    assert base and all(r["overall"] in ("pass", "fail") for r in base)
    strict = pt.filter_brainswipes(window.sessions, minimums={"avgT1": 0.9})
    assert 0 < len(strict) < len(base)
    assert all(r["avgT1"] >= 0.9 for r in strict)
    few_fails = pt.filter_brainswipes(window.sessions, maximums={"T1_fails": 0})
    assert all(r["T1_fails"] == 0 for r in few_fails)
    done = pt.filter_brainswipes(window.sessions, require_complete=True)
    assert all(window.sessions[(r["participant_id"], r["session_id"])].stage_status["XCP-D"] == "success"
               for r in done)


def test_passable_list_merges_by_recon(window):
    window.import_file(str(BS_RESULTS))
    before = len(pt.filter_brainswipes(window.sessions))
    window.import_file(str(BS_PASSABLE))
    assert len(pt.filter_brainswipes(window.sessions)) == before


def test_unknown_sessions_warn_on_terminal(window, capsys):
    pid, sid = next(iter(window.sessions))
    f = window.tmp_path / "Oct-15_v9_nibabies_v1_audit_report.csv"
    f.write_text(f"participant_id,session_id,pending,success,errored\n"
                 f"{pid},{sid},FALSE,TRUE,FALSE\nsub-nope,ses-1mo,FALSE,TRUE,FALSE\n")
    report = window.import_file(str(f))
    err = capsys.readouterr().err
    assert "[WARNING] Oct-15_v9_nibabies_v1_audit_report.csv" in err and "sub-nope_ses-1mo" in err
    assert report.updated == 1


def test_errors_are_per_version_and_deduplicated(window):
    err = str(XCPD_ERRORS)  # version "main_folder_v0.10.7", the active XCP-D version
    window.import_file(err)
    window.import_file(err)

    errored = [s for s in window.sessions.values() if s.errors.get("XCP-D")]
    assert errored
    assert all(len(s.errors["XCP-D"]) == len({e["Error_Log_Paths"] for e in s.errors["XCP-D"]})
               for s in errored)
    s = errored[0]
    assert s.stage_status["XCP-D"] == "error" and s.current_stage == "XCP-D"

    # a different version is unaffected by those errors
    window.import_file(str(SAMPLES / "Oct-15_anat_rerun_xcpd_v0.10.7_error_report_no_low_motion_runs.csv"))
    window.active_versions["XCP-D"] = "anat_rerun_v0.10.7"
    window.recompute()
    assert "anat_rerun_v0.10.7" in window.versions("XCP-D")
    window.active_versions["XCP-D"] = "main_folder_v0.10.7"
    window.recompute()
    assert s.errors.get("XCP-D")

    # a later success for the same version clears its errors
    s.set_status("XCP-D", "main_folder_v0.10.7", "success")
    window.recompute()
    assert not s.errors.get("XCP-D") and s.current_stage == "Complete"


def test_notes_import(window):
    pid, sid = next(iter(window.sessions))
    notes = window.tmp_path / "Oct-15_x_notes_report.csv"
    notes.write_text(f"participant_id,session_id,notes\n{pid},{sid},missing scans\nsub-nope,ses-1mo,x\n")
    report = window.import_file(str(notes))
    assert report.updated == 1
    assert ImportUnknown in report.skipped
    assert window.sessions[(pid, sid)].notes == ["missing scans"]


ImportUnknown = pt.ImportReport.UNKNOWN


def test_version_combo_toggles_stage(window):
    f = window.tmp_path / "Oct-15_alt_nibabies_v1_audit_report.csv"
    f.write_text("participant_id,session_id,pending,success,errored\n" + "\n".join(
        f"{p},{s},FALSE,FALSE,TRUE" for p, s in window.sessions) + "\n")
    window.import_file(str(f))
    window.rebuild_version_controls()
    combo = next(w for w in window.findChildren(pt.QComboBox) if w.findText("alt_v1") >= 0)
    before = stage_counts(window)["Complete"]
    combo.setCurrentText("alt_v1")
    assert window.active_versions["Nibabies"] == "alt_v1"
    assert stage_counts(window)["Complete"] == 0 < before


def test_every_sample_file_follows_schema_and_imports(window):
    paths = sorted(p for p in list(DATA.glob("*.csv")) + list(SAMPLES.rglob("*.csv")))
    assert paths
    for path in paths:
        assert pt.parse_csv_filename(str(path)), f"{path.name} does not follow the naming schema"
        window.import_file(str(path))
    assert "main_folder_v25.0.1" in window.versions("Nibabies")
    assert set(window.versions("Nibabies")) >= {"main_folder_v25.0.1", "anat_only_v25.0.1", "corrected_anat_runs_v25.0.1", "extra_mcribs_v25.0.1"}
    assert set(window.versions("XCP-D")) >= {"main_folder_v0.10.7", "anat_rerun_v0.10.7"}
    assert window.versions("MRIQC") == ["pilot_v1"]
    window.rebuild_version_controls()
    for view in (window.show_pipeline_view, window.show_overview,
                 window.show_error_summary, window.show_brainswipes_view):
        view()


# ---- filters, export, summary, comparison, sessions, validation --------------------------

def import_errors(w):
    w.import_file(str(XCPD_ERRORS))
    w.import_file(str(SAMPLES / "Oct-15_anat_rerun_xcpd_v0.10.7_error_report_no_low_motion_runs.csv"))
    w.refresh_all()


def test_filters(window):
    total = len(window.sessions)
    assert len(window.filtered_sessions()) == total
    first = sorted(window.sessions)[0]
    window.filters.update(text=first[0])
    assert all(s.participant_id == first[0] for s in window.filtered_sessions())
    window.filters.update(text="", stage="Complete")
    assert {s.current_stage for s in window.filtered_sessions()} == {"Complete"}
    window.filters.update(stage="Any", status="error")
    assert all(window.current_status(s) == "error" for s in window.filtered_sessions())
    window.filters.update(status="Any", notes=True)
    assert window.filtered_sessions() == []


def test_filter_widgets_drive_pipeline_view(window):
    window.filter_stage.setCurrentText("Complete")
    assert window.filters["stage"] == "Complete"
    window.clear_filters()
    assert window.filters == pt.PipelineConfig.DEFAULT_FILTERS


def test_error_filter(window):
    import_errors(window)
    window.active_versions["XCP-D"] = "main_folder_v0.10.7"
    window.recompute()
    names = window.error_csv_names()
    assert names
    window.filters["error"] = names[0]
    assert window.filtered_sessions()


def test_export_current_view(window):
    import pandas as pd
    out = window.tmp_path / "view.csv"
    window.filters["stage"] = "Complete"
    window.export_current_view(str(out))
    df = pd.read_csv(out)
    assert set(df["current_stage"]) == {"Complete"}
    assert {"participant_id", "session_id", "XCP-D_version", "XCP-D_status", "n_errors"} <= set(df.columns)


def test_summary(window):
    d = window.summary_data()
    assert d["total"] == len(window.sessions)
    assert d["complete"] + len(d["incomplete"]) == d["total"]
    text = window.summary_text()
    assert "Per stage and version" in text and "main_folder_v0.10.7*" in text
    paths = window.save_summary(str(window.tmp_path / "rep.txt"))
    import pandas as pd
    assert len(pd.read_csv(paths[1])) == len(d["incomplete"])


def test_version_comparison(window):
    import_errors(window)
    rows = window.compare_versions("XCP-D", "main_folder_v0.10.7", "anat_rerun_v0.10.7")
    assert rows and all(r["status_a"] != r["status_b"] for r in rows)
    assert {r["change"] for r in rows} <= {"only_in_a", "only_in_b", "improved", "regressed", "changed"}
    window.switch_view("Version Comparison")
    window.comparison.update(stage="XCP-D", a="main_folder_v0.10.7", b="anat_rerun_v0.10.7")
    out = window.tmp_path / "cmp.csv"
    window.view_combo.setCurrentText("Version Comparison")
    window.export_current_view(str(out))
    assert out.exists()


def test_all_views_render(window):
    import_errors(window)
    for view in ["Pipeline View", "Overview", "Error Summary", "BrainSwipes QC",
                 "Version Comparison", "Summary"]:
        window.view_combo.setCurrentText(view)


def test_save_and_load_session(window, app):
    import_errors(window)
    window.import_file(str(BS_RESULTS))
    window.active_versions["XCP-D"] = "anat_rerun_v0.10.7"
    window.recompute()
    before = {k: (s.current_stage, dict(s.stage_status)) for k, s in window.sessions.items()}
    path = window.save_session(str(window.tmp_path / "s.json"))

    fresh = pt.PipelineTrackerWindow(str(DATA / "bcp_participants.tsv"), None)
    assert fresh.load_session(path) == []
    assert fresh.active_versions["XCP-D"] == "anat_rerun_v0.10.7"
    assert {k: (s.current_stage, dict(s.stage_status)) for k, s in fresh.sessions.items()} == before


def test_load_session_reports_missing_file(window):
    path = window.save_session(str(window.tmp_path / "s.json"))
    import json
    data = json.loads(Path(path).read_text())
    data["imports"][0].update(path="/nope/x.csv", relative="nope/x.csv")
    Path(path).write_text(json.dumps(data))
    messages = window.load_session(path)
    assert len(messages) == 1 and "not found" in messages[0]


def test_import_folder(app):
    w = pt.PipelineTrackerWindow(str(DATA / "bcp_participants.tsv"), None)
    summaries = w.import_folder(str(SAMPLES))
    assert any("FAILED" not in t and "skipped" not in t for t in summaries)
    assert {"main_folder_v25.0.1", "anat_only_v25.0.1", "corrected_anat_runs_v25.0.1", "extra_mcribs_v25.0.1"} <= set(w.versions("Nibabies"))


def test_import_folder_skips_unnamed_files(app, tmp_path):
    (tmp_path / "random.csv").write_text("a,b\n1,2\n")
    w = pt.PipelineTrackerWindow(str(DATA / "bcp_participants.tsv"), None)
    summaries = w.import_folder(str(tmp_path))
    assert "does not follow the schema" in summaries[0] and "xcpd" in summaries[0]


def test_column_validation(window, tmp_path):
    bad = tmp_path / "Oct-15_bad_xcpd_v9_audit_report.csv"
    bad.write_text("foo,bar\n1,2\n")
    with pytest.raises(ValueError, match="participant column"):
        window.import_file(str(bad))
    bad2 = tmp_path / "Oct-15_bad_xcpd_v10_audit_report.csv"
    bad2.write_text("participant_id,session_id,x\nsub-1,ses-1,2\n")
    with pytest.raises(ValueError, match="at least one of"):
        window.import_file(str(bad2))


def test_cli_accepts_participants_tsv_and_alias(monkeypatch):
    import argparse
    seen = {}
    monkeypatch.setattr(pt, "QApplication", lambda *a: (_ for _ in ()).throw(SystemExit(0)))
    for flag in ("--participants_tsv", "--input", "--participants-tsv"):
        monkeypatch.setattr(sys, "argv", ["x", flag, str(DATA / "bcp_participants.tsv")])
        with pytest.raises(SystemExit) as e:
            pt.main()
        assert e.value.code == 0
    monkeypatch.setattr(sys, "argv", ["x"])
    with pytest.raises(SystemExit) as e:
        pt.main()
    assert e.value.code == 2


AUDIT_REPORTS = ROOT / "bcp_processing_audit_tests_Mar20-2026"


def test_audit_report_status_rules():
    f = pt.PipelineTrackerWindow._audit_report_status
    assert f({"status": "success?", "exec_sum": "FOUND_EXEC-SUM", "crash_log": ""}) == "success"
    assert f({"status": "failed?", "exec_sum": "NO_OUTPUTS", "crash_log": ""}) == "pending"
    assert f({"status": "failed?", "exec_sum": "NO_EXEC-SUM", "crash_log": ""}) == "error"
    assert f({"status": "failed?", "exec_sum": "NO_OUTPUTS", "crash_log": "x.txt"}) == "error"


@pytest.mark.skipif(not AUDIT_REPORTS.exists(), reason="audit report folder not present")
def test_import_audit_report_folder(window):
    summaries = window.import_folder(str(AUDIT_REPORTS))
    assert not any("FAILED" in t or "skipped" in t for t in summaries)
    assert {"main_folder_v25.0.1", "reproc-mfc_v25.0.1"} <= set(window.versions("Nibabies"))
    window.active_versions["Nibabies"] = "main_folder_v25.0.1"
    window.recompute()
    assert sum(s.stage_status["Nibabies"] == "success" for s in window.sessions.values()) == 864


def test_import_folder_skips_outdated(app):
    w = pt.PipelineTrackerWindow(str(DATA / "bcp_participants.tsv"), None)
    w.import_folder(str(DATA))
    assert "pilot_v25.0.1" not in w.versions("Nibabies")
    assert "main_folder_v25.0.1" in w.versions("Nibabies")
