"""
BCP Processing Tracker GUI
A PyQt6 application for tracking BCP processing sessions through different pipeline stages.

Author: lundq163
Date: October 2025
"""

import sys
import argparse
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Set
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QScrollArea, QDialog, QTextEdit, QFileDialog,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QGroupBox, QGridLayout, QFrame, QMessageBox,
    QLineEdit, QSizePolicy, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QPalette, QFont


# ============================================================================
# CONFIGURATION SECTION - MAINTAINERS: Modify stages and headers here
# ============================================================================

class PipelineConfig:
    """
    Configuration class for pipeline stages and CSV headers.
    
    MAINTAINERS: 
    - Add/remove stages in STAGES list
    - Update CSV_HEADERS for each stage with expected column names
    - Modify ERROR_CSV_HEADERS if error query format changes
    """
    
    # List of all processing stages in order
    # TO ADD A STAGE: Add stage name to this list in desired position
    # TO REMOVE A STAGE: Comment out or remove from this list
    STAGES = [
        "Setup",
        "MRIQC",
        "BIBSNet",
        "Nibabies",
        "XCP-D",
        "Complete"
    ]

    # Data sources that annotate sessions but are not pipeline columns
    OVERLAY_STAGES = ["BrainSwipes QC", "Notes"]

    # Stage whose success marks a session Complete
    COMPLETE_AFTER = "XCP-D"

    # Stages that have pipeline versions (and can have error-query CSVs)
    VERSIONED_STAGES = ["MRIQC", "BIBSNet", "Nibabies", "XCP-D"]

    # Stages imported from a pending/success/errored tracking CSV
    STATUS_STAGES = ["BIBSNet", "Nibabies", "XCP-D"]

    # Version used by sources that are not versioned
    UNVERSIONED = "all"

    # Filename prefix -> stage for the CSV naming schema:
    #   {stage}__{version}__{audit|errors}[__label].csv
    STAGE_TOKENS = {
        "mriqc": "MRIQC",
        "bibsnet": "BIBSNet",
        "nibabies": "Nibabies",
        "xcpd": "XCP-D",
        "brainswipes": "BrainSwipes QC",
        "notes": "Notes",
    }

    # Header tooltips
    STAGE_NOTES = {
        "BIBSNet": "Segmentations are QC'd manually; status comes from the tracking CSV, not an automated audit.",
        "Complete": "Reached when XCP-D succeeds.",
    }

    # BrainSwipes columns that can be used to filter sessions: (column, label, kind, default)
    # kind "min" keeps rows >= value, "max" keeps rows <= value
    BRAINSWIPES_METRICS = [
        ("avgT1", "avg T1", "min", 0.7),
        ("avgT2", "avg T2", "min", 0.7),
        ("avgFunc", "avg Func", "min", 0.7),
        ("T1_passes", "T1 passes", "min", 1),
        ("T2_passes", "T2 passes", "min", 1),
        ("func_passes", "Func passes", "min", 1),
        ("T1_fails", "T1 fails", "max", 2),
        ("T2_fails", "T2 fails", "max", 2),
        ("func_fails", "Func fails", "max", 2),
    ]
    
    # CSV headers expected for each stage
    # MAINTAINERS: Update these dictionaries with actual column names
    CSV_HEADERS = {
        "Setup": {
            "required": ["participant_id", "session_id"],
            "optional": []
        },
        
        "MRIQC": {
            # First CSV: Best anatomical scan selection
            "best_anatomical": ["participant_id", "session_id", "best_T1_scan_id", "best_T2_scan_id"],
            # Second CSV: Quality metrics
            "quality_metrics": ["participant_id", "session_id", "run", "modality", 
                              "fwhm_avg", "snr_total", "snr_gm", "snr_wm"],
            # Third CSV: BCP anatomical counts
            "bcp_bids_anat_counts": ["participant_id", "session_id", "t1_count", "t2_count"],
            "anat_qc_all": ["participant_id", "session_id", "attempt", "n_attempts", "best_t1_run", "best_t2_run", "sheet", "attempt_t1", "attempt_t2"],
            "series_run_key_output": ["participant_id", "session_id", "mode", "bids_run", "dicom_series"],
            # MAINTAINERS: Add additional MRIQC CSV formats here as needed
            # Example:
            # "additional_metrics": ["participant_id", "session_id", "other_metric"],
        },
        
        "BIBSNet": {
            # MAINTAINERS: Fill in actual BIBSNet status CSV headers below
            "bibsnet_tracking": ["participant_id", "session_id", "pending", "success", "errored", "T1_only", "T2_only", "T1&T2"],
            # Example: ["participant_id", "session_id", "status", "output_path"]
        },
        
        "Nibabies": {
            # MAINTAINERS: Fill in actual Nibabies status CSV headers below
            "status": ["participant_id", "session_id", "pending", "success", "errored"],  # Add actual headers
            # Example: ["participant_id", "session_id", "completion_status", "runtime"]
        },
        
        "XCP-D": {
            # MAINTAINERS: Fill in actual XCP-D status CSV headers below
            "status": ["participant_id", "session_id", "pending", "success", "errored"],  # Add actual headers
            # Example: ["participant_id", "session_id", "processing_complete", "quality_flag"]
        },
        
        "BrainSwipes QC": {
            "status": ["participant_id", "session_id"],  # Add actual headers
            # MAINTAINERS: Add BrainSwipes-specific headers
            # Example: ["participant_id", "session_id", "qc_pass", "qc_score", "category"]
        }
    }
    
    # Error query CSV headers (applies to any processing stage)
    ERROR_CSV_HEADERS = ["Subject_IDs", "Session_IDs", "Run_Number", "Error_Log_Paths"]
    
    # Stage colors for visual differentiation
    STAGE_COLORS = {
        "Setup": "#E8F4F8",
        "MRIQC": "#D4E9F7",
        "BIBSNet": "#C1DDF5",
        "Nibabies": "#ADD2F3",
        "XCP-D": "#9AC7F1",
        "Complete": "#B8E6B8"
    }


def filter_brainswipes(sessions, recon=None, overall=None, minimums=None, maximums=None,
                       require_complete=False) -> List[Dict]:
    """Returns one dict per BrainSwipes recon row (across sessions) that meets every criterion.
    Missing scores never satisfy an active min/max criterion."""
    minimums = minimums or {}
    maximums = maximums or {}
    out = []
    for key in sorted(sessions):
        session = sessions[key]
        if require_complete and session.stage_status.get(PipelineConfig.COMPLETE_AFTER) != "success":
            continue
        for row in session.stage_data.get("BrainSwipes QC", {}).get("recons", []):
            if recon and row.get("recon") != recon:
                continue
            if overall and row.get("overall") != overall:
                continue
            if any(not (pd.notna(row.get(c)) and row[c] >= v) for c, v in minimums.items()):
                continue
            if any(not (pd.notna(row.get(c)) and row[c] <= v) for c, v in maximums.items()):
                continue
            out.append({"participant_id": session.participant_id,
                        "session_id": session.session_id, **row})
    return out


class ImportReport:
    """Collects what an import did so the user can see what was skipped and why."""

    UNKNOWN = "not in participants.tsv"

    def __init__(self):
        self.updated = 0
        self.skipped: Dict[str, List[str]] = {}

    def skip(self, reason: str, label: str):
        self.skipped.setdefault(reason, []).append(str(label))

    def summary(self) -> str:
        lines = [f"Updated {self.updated} session(s)."]
        for reason, labels in self.skipped.items():
            example = ", ".join(labels[:3])
            lines.append(f"Skipped {len(labels)}: {reason} (e.g. {example})")
        return "\n".join(lines)


# ============================================================================
# DATA MODELS
# ============================================================================

def parse_csv_filename(path: str) -> Optional[Dict[str, str]]:
    """Parses the required CSV naming schema: {stage}__{version}__{audit|errors}[__label].csv
    Returns {"stage", "version", "kind", "label"} or None if the name does not follow the schema."""
    parts = Path(path).stem.split("__")
    if len(parts) < 3:
        return None
    token, version, kind = parts[0].lower(), parts[1], parts[2].lower()
    stage = PipelineConfig.STAGE_TOKENS.get(token)
    if stage is None or not version or kind not in ("audit", "errors"):
        return None
    if kind == "errors" and stage not in PipelineConfig.VERSIONED_STAGES:
        return None
    return {"stage": stage, "version": version, "kind": kind, "label": "__".join(parts[3:])}


class SessionData:
    """Stores all data for a single session across all pipeline stages and pipeline versions.

    Raw data lives in `runs[stage][version]`. The flat attributes `stage_data`, `stage_status`,
    `errors` and `current_stage` are the view of the currently selected version of each stage and
    are refreshed by PipelineTrackerWindow.recompute().
    """

    def __init__(self, participant_id: str, session_id: str):
        self.participant_id = participant_id
        self.session_id = session_id
        self.runs: Dict[str, Dict[str, Dict]] = {}  # stage -> version -> {"data", "status", "errors"}
        self.active_versions: Dict[str, str] = {}  # shared with the window; used by the detail dialog
        self.current_stage = "Setup"
        self.stage_data = {}
        self.stage_status = {}  # stage -> "success" | "error" | "pending"
        self.errors = {}  # stage -> list of error info
        self.notes = []  # Free-text notes

    def get_display_name(self) -> str:
        """Returns formatted display name for the session."""
        return f"{self.participant_id}_{self.session_id}"

    def run(self, stage: str, version: str) -> Dict:
        """Returns (creating if needed) the record for one stage and pipeline version."""
        return self.runs.setdefault(stage, {}).setdefault(
            version, {"data": {}, "status": None, "errors": []})

    def update_stage_data(self, stage: str, version: str, data: Dict):
        self.run(stage, version)["data"].update(data)

    def set_status(self, stage: str, version: str, status: str):
        """Records a status. A success supersedes earlier errors for that version."""
        run = self.run(stage, version)
        run["status"] = status
        if status == "success":
            run["errors"] = []

    def add_error(self, stage: str, version: str, error_info: Dict):
        run = self.run(stage, version)
        if error_info not in run["errors"]:
            run["errors"].append(error_info)
        run["status"] = "error"




# ============================================================================
# SESSION TILE WIDGET
# ============================================================================

class SessionTile(QFrame):
    """Visual tile representing a single session."""
    
    clicked = pyqtSignal(str, str)  # participant_id, session_id
    
    def __init__(self, session: SessionData, parent=None):
        super().__init__(parent)
        self.session = session
        self.setup_ui()

        
    def setup_ui(self):
        """Sets up the tile appearance."""
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.setLineWidth(2)
        # Make tiles expand horizontally to fill the stage column, keep a compact fixed height
        self.setFixedHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Session name label
        name_label = QLabel(self.session.get_display_name())
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setWordWrap(True)
        font = QFont()
        font.setBold(True)
        font.setPointSize(9)
        name_label.setFont(font)
        
        # Status indicator
        status = self.session.stage_status.get(self.session.current_stage, "pending")
        status_label = QLabel(f"●")
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_font = QFont()
        status_font.setPointSize(16)
        status_label.setFont(status_font)
        
        if status == "success":
            status_label.setStyleSheet("color: green;")
        elif status == "error":
            status_label.setStyleSheet("color: red;")
        else:
            status_label.setStyleSheet("color: gray;")
        
        layout.addWidget(name_label)
        layout.addWidget(status_label)
        
        self.setLayout(layout)
        
        if self.session.notes:
            self.setToolTip("\n".join(self.session.notes))
            name_label.setText(f"⚠ {self.session.get_display_name()}")
        
        stage_color = PipelineConfig.STAGE_COLORS.get(self.session.current_stage, "#FFFFFF")
        self.setStyleSheet(f"background-color: {stage_color}; border-radius: 5px;")
    
    def mousePressEvent(self, event):
        """Handles click events on the tile."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.session.participant_id, self.session.session_id)
        super().mousePressEvent(event)


# ============================================================================
# SESSION DETAIL DIALOG
# ============================================================================

class SessionDetailDialog(QDialog):
    """Dialog showing detailed information about a session."""
    
    def __init__(self, session: SessionData, parent=None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle(f"Session Details: {session.get_display_name()}")
        self.setMinimumSize(700, 500)
        self.setup_ui()
        
    def setup_ui(self):
        """Sets up the dialog UI."""
        layout = QVBoxLayout()
        
        # Header
        header = QLabel(f"<h2>{self.session.get_display_name()}</h2>")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)
        
        # Current stage
        stage_label = QLabel(f"<b>Current Stage:</b> {self.session.current_stage}")
        layout.addWidget(stage_label)
        
        # Tab widget for different data views
        tabs = QTabWidget()
        
        # Stage Data Tab
        stage_tab = QWidget()
        stage_layout = QVBoxLayout()
        stage_scroll = QScrollArea()
        stage_scroll.setWidgetResizable(True)
        stage_content = QWidget()
        stage_content_layout = QVBoxLayout()
        
        for stage in PipelineConfig.STAGES + PipelineConfig.OVERLAY_STAGES:
            for version, run in self.session.runs.get(stage, {}).items():
                active = version == PipelineConfig.UNVERSIONED or \
                    self.session.active_versions.get(stage) == version
                title = stage if version == PipelineConfig.UNVERSIONED else f"{stage} - {version}"
                group = QGroupBox(title + ("" if active or version == PipelineConfig.UNVERSIONED
                                           else " (not selected)"))
                group_layout = QVBoxLayout()
                
                data_text = QTextEdit()
                data_text.setReadOnly(True)
                data_text.setMaximumHeight(150)
                
                # Format stage data
                data_str = ""
                for key, value in run["data"].items():
                    if key == "recons":
                        for r in value:
                            scores = ", ".join(f"{k}={v}" for k, v in r.items() if k != "recon")
                            data_str += f"recon {r.get('recon')}: {scores}\n"
                    else:
                        data_str += f"{key}: {value}\n"
                
                data_text.setText(data_str if data_str else "No data available")
                group_layout.addWidget(data_text)
                
                # Status
                status = run["status"] or "pending"
                status_label = QLabel(f"Status: {status.upper()}")
                if status == "success":
                    status_label.setStyleSheet("color: green; font-weight: bold;")
                elif status == "error":
                    status_label.setStyleSheet("color: red; font-weight: bold;")
                group_layout.addWidget(status_label)
                
                group.setLayout(group_layout)
                stage_content_layout.addWidget(group)
        
        stage_content.setLayout(stage_content_layout)
        stage_scroll.setWidget(stage_content)
        stage_layout.addWidget(stage_scroll)
        stage_tab.setLayout(stage_layout)
        tabs.addTab(stage_tab, "Stage Data")
        
        # Errors Tab
        errors_tab = QWidget()
        errors_layout = QVBoxLayout()
        errors_text = QTextEdit()
        errors_text.setReadOnly(True)
        
        error_content = ""
        for stage, versions in self.session.runs.items():
            for version, run in versions.items():
                if not run["errors"]:
                    continue
                error_content += f"=== {stage} - {version} ===\n"
                for idx, error in enumerate(run["errors"], 1):
                    error_content += f"\nError {idx}:\n"
                    for key, value in error.items():
                        error_content += f"  {key}: {value}\n"
                error_content += "\n"
        
        errors_text.setText(error_content if error_content else "No errors recorded")
        errors_layout.addWidget(errors_text)
        errors_tab.setLayout(errors_layout)
        tabs.addTab(errors_tab, "Errors")
        
        if self.session.notes:
            notes_text = QTextEdit()
            notes_text.setReadOnly(True)
            notes_text.setText("\n".join(self.session.notes))
            tabs.addTab(notes_text, "Notes")
        
        layout.addWidget(tabs)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)


# ============================================================================
# MAIN APPLICATION WINDOW
# ============================================================================

class PipelineTrackerWindow(QMainWindow):

    """Main application window."""

    def _extract_ids(self, row) -> Optional[tuple]:
        """Extract (participant_id, session_id) from a row with flexible header names.
        Normalizes to BIDS format (sub-XXX, ses-XXX) if needed.
        Returns (pid, sid) or None if not found.
        """
        pid_keys = ['participant_id', 'Subject_IDs', 'subject_id', 'participant', 'subject', 'sub']
        sid_keys = ['session_id', 'Session_IDs', 'session', 'ses', 'sess']
        pid = None
        sid = None
        # pandas Series supports `in` for labels; also row.get works
        for k in pid_keys:
            if k in row and pd.notna(row.get(k)):
                pid = str(row.get(k)).strip()
                break
        for k in sid_keys:
            if k in row and pd.notna(row.get(k)):
                sid = str(row.get(k)).strip()
                break
        if pid and sid:
            # Normalize to BIDS format if not already
            if not pid.startswith('sub-'):
                pid = f'sub-{pid}'
            if not sid.startswith('ses-'):
                sid = f'ses-{sid}'
            return pid, sid
        return None
    
    def __init__(self, initial_csv: str, stages: List[str]):
        super().__init__()
        self.sessions = {}  # Dict of (participant_id, session_id) -> SessionData
        self.stages = stages if stages else PipelineConfig.STAGES
        self.active_versions = {}  # stage -> selected pipeline version
        self.current_view = "Pipeline"  # "Pipeline" | "Overview" | "Errors" | "BrainSwipes"
        
        # Load initial sessions
        self.load_initial_sessions(initial_csv)
        for session in self.sessions.values():
            session.active_versions = self.active_versions
        self.recompute()
        
        self.setWindowTitle("Processing Stage Tracker")
        self.setMinimumSize(1200, 800)
        self.setup_ui()

    def versions(self, stage: str) -> List[str]:
        """Pipeline versions that have been imported for a stage (in import order)."""
        seen = []
        for session in self.sessions.values():
            for version in session.runs.get(stage, {}):
                if version not in seen:
                    seen.append(version)
        return seen

    def stage_label(self, stage: str) -> str:
        version = self.active_versions.get(stage)
        return f"{stage} ({version})" if version else stage

    def set_active_version(self, stage: str, version: str):
        self.active_versions[stage] = version
        self.recompute()
        self.switch_view(self.view_combo.currentText())

    def recompute(self):
        """Refreshes every session's flat view from the selected version of each stage.

        A session advances through the stages in order; it stops at the first stage that is not
        successful. A stage with no data for the selected version leaves it at the last
        successful stage. XCP-D success means Complete.
        """
        for stage in PipelineConfig.VERSIONED_STAGES:
            versions = self.versions(stage)
            if versions and self.active_versions.get(stage) not in versions:
                self.active_versions[stage] = versions[0]

        walk = [s for s in self.stages if s not in ("Setup", "Complete")]
        for session in self.sessions.values():
            session.stage_data, session.stage_status, session.errors = {}, {}, {}
            for stage, versions in session.runs.items():
                version = (PipelineConfig.UNVERSIONED if stage in PipelineConfig.OVERLAY_STAGES
                           else self.active_versions.get(stage))
                run = versions.get(version)
                if run is None:
                    continue
                session.stage_data[stage] = run["data"]
                if run["errors"]:
                    session.errors[stage] = run["errors"]
                status = run["status"] or "pending"
                session.stage_status[stage] = status

            current = self.stages[0]
            complete = False
            for stage in walk:
                status = session.stage_status.get(stage)
                if status is None:
                    break
                current = stage
                if status != "success":
                    break
                if stage == PipelineConfig.COMPLETE_AFTER and "Complete" in self.stages:
                    current, complete = "Complete", True
                    break
            session.current_stage = current
            if complete:
                session.stage_status["Complete"] = "success"

    def rebuild_version_controls(self):
        """One version picker per pipeline stage that has imported versions."""
        while self.version_layout.count():
            item = self.version_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for stage in PipelineConfig.VERSIONED_STAGES:
            versions = self.versions(stage)
            if not versions or stage not in self.stages:
                continue
            self.version_layout.addWidget(QLabel(f"{stage}:"))
            combo = QComboBox()
            combo.addItems(versions)
            combo.setCurrentText(self.active_versions[stage])
            combo.currentTextChanged.connect(lambda v, s=stage: self.set_active_version(s, v))
            self.version_layout.addWidget(combo)
        self.version_layout.addStretch()

    def warn_unknown_sessions(self, filename: str, report: ImportReport):
        """Prints sessions that are not in the canonical participants.tsv to the terminal."""
        unknown = sorted(set(report.skipped.get(ImportReport.UNKNOWN, [])))
        if unknown:
            print(f"[WARNING] {filename}: {len(unknown)} session(s) not in participants.tsv:",
                  file=sys.stderr)
            for label in unknown:
                print(f"    {label}", file=sys.stderr)

    def load_initial_sessions(self, tsv_path: str):
        """Loads initial sessions from BIDS participants.tsv file."""
        try:
            # Read TSV file (tab-separated)
            df = pd.read_csv(tsv_path, sep='\t')
            df.columns = df.columns.str.strip()
            
            # BIDS standard uses 'participant_id' and 'session_id' columns
            # participant_id format: sub-XXXXX
            # session_id format: ses-XXXXX
            
            if 'participant_id' not in df.columns:
                raise ValueError("BIDS participants.tsv must contain 'participant_id' column")
            
            if 'session_id' not in df.columns:
                raise ValueError("BIDS participants.tsv must contain 'session_id' column")
            
            for _, row in df.iterrows():
                participant_id = str(row['participant_id']).strip()
                session_id = str(row['session_id']).strip()
                
                # Validate BIDS format
                if not participant_id.startswith('sub-'):
                    print(f"Warning: participant_id '{participant_id}' doesn't follow BIDS format (sub-XXX)")
                if not session_id.startswith('ses-'):
                    print(f"Warning: session_id '{session_id}' doesn't follow BIDS format (ses-XXX)")
                
                session = SessionData(participant_id, session_id)
                self.sessions[(participant_id, session_id)] = session
                
            print(f"Loaded {len(self.sessions)} sessions from BIDS participants.tsv: {tsv_path}")
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to load BIDS participants.tsv: {str(e)}")
            sys.exit(1)
    
    def setup_ui(self):
        """Sets up the main UI."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Top menu bar
        menu_layout = QHBoxLayout()
        
        # View switcher
        view_label = QLabel("View:")
        menu_layout.addWidget(view_label)
        
        self.view_combo = QComboBox()
        self.view_combo.addItems(["Pipeline View", "Overview", "Error Summary", "BrainSwipes QC"])
        self.view_combo.currentTextChanged.connect(self.switch_view)
        menu_layout.addWidget(self.view_combo)
        
        menu_layout.addStretch()
        
        # Import buttons
        import_btn = QPushButton("Import CSV(s)")
        import_btn.clicked.connect(self.import_csv)
        menu_layout.addWidget(import_btn)
        
        import_error_btn = QPushButton("Import Error CSV(s)")
        import_error_btn.clicked.connect(lambda: self.import_csv(kind="errors"))
        menu_layout.addWidget(import_error_btn)
        
        export_btn = QPushButton("Export Complete Sessions")
        export_btn.clicked.connect(self.export_complete_sessions)
        menu_layout.addWidget(export_btn)
        
        main_layout.addLayout(menu_layout)

        # Pipeline version pickers (filled in as versions are imported)
        self.version_layout = QHBoxLayout()
        main_layout.addLayout(self.version_layout)
        self.rebuild_version_controls()
        
        # Content area (will be populated based on view)
        self.content_widget = QWidget()
        main_layout.addWidget(self.content_widget)
        
        # Initialize with pipeline view
        self.show_pipeline_view()
    
    def switch_view(self, view_name: str):
        """Switches between different views."""
        if view_name == "Pipeline View":
            self.show_pipeline_view()
        elif view_name == "Overview":
            self.show_overview()
        elif view_name == "Error Summary":
            self.show_error_summary()
        elif view_name == "BrainSwipes QC":
            self.show_brainswipes_view()
    
    def show_pipeline_view(self):
        """Shows the main pipeline view with each session as a row and stages as columns."""
        # Clear existing content
        if self.content_widget.layout():
            QWidget().setLayout(self.content_widget.layout())

        layout = QVBoxLayout()

        # Build a table: rows = sessions, columns = stages
        table = QTableWidget()
        table.setColumnCount(len(self.stages))
        table.setHorizontalHeaderLabels([self.stage_label(s) for s in self.stages])
        for col_idx, stage in enumerate(self.stages):
            note = PipelineConfig.STAGE_NOTES.get(stage)
            if note:
                table.horizontalHeaderItem(col_idx).setToolTip(note)

        # Stable ordering of sessions for rows
        session_keys = sorted(self.sessions.keys(), key=lambda k: (k[0], k[1]))
        table.setRowCount(len(session_keys))

        # Set vertical headers to session display names
        for row_idx, (pid, sid) in enumerate(session_keys):
            display_name = f"{pid}_{sid}"
            item = QTableWidgetItem(display_name)
            table.setVerticalHeaderItem(row_idx, item)

        # Populate tiles: place the SessionTile only in the column of the current stage
        for row_idx, key in enumerate(session_keys):
            session = self.sessions[key]
            if session.current_stage in self.stages:
                col_idx = self.stages.index(session.current_stage)
                tile = SessionTile(session)
                tile.clicked.connect(self.show_session_details)
                table.setCellWidget(row_idx, col_idx, tile)

        # Sizing behavior: stretch columns, set row height to fit tiles
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        vheader = table.verticalHeader()
        vheader.setDefaultSectionSize(90)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)

        layout.addWidget(table)
        self.content_widget.setLayout(layout)
    
    def show_overview(self):
        """Shows overview statistics for each stage."""
        if self.content_widget.layout():
            QWidget().setLayout(self.content_widget.layout())
        
        layout = QVBoxLayout()
        
        title = QLabel("<h2>Pipeline Overview</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Create table
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels([
            "Stage", 
            "Remaining Sessions", 
            "Known Successful", 
            "Known Fail", 
            "Unidentified"
        ])
        table.setRowCount(len(self.stages))
        
        for idx, stage in enumerate(self.stages):
            sessions_in_stage = [s for s in self.sessions.values() if s.current_stage == stage]
            total = len(sessions_in_stage)
            successful = sum(1 for s in sessions_in_stage if s.stage_status.get(stage) == "success")
            errors = sum(1 for s in sessions_in_stage if s.stage_status.get(stage) == "error")
            unidentified = max(total - successful - errors, 0)
            
            table.setItem(idx, 0, QTableWidgetItem(self.stage_label(stage)))
            table.setItem(idx, 1, QTableWidgetItem(str(total)))
            table.setItem(idx, 2, QTableWidgetItem(str(successful)))
            table.setItem(idx, 3, QTableWidgetItem(str(errors)))
            table.setItem(idx, 4, QTableWidgetItem(str(unidentified)))
        
        table.resizeColumnsToContents()
        layout.addWidget(table)
        
        self.content_widget.setLayout(layout)
    
    def show_error_summary(self):
        """Shows summary of errors across all stages."""
        if self.content_widget.layout():
            QWidget().setLayout(self.content_widget.layout())
        
        layout = QVBoxLayout()
        
        title = QLabel("<h2>Error Summary</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout()
        
        for stage in self.stages:
            # Count errors for this stage
            sessions_with_errors = [s for s in self.sessions.values() 
                                  if stage in s.errors and s.errors[stage]]
            
            if sessions_with_errors:
                stage_group = QGroupBox(f"{self.stage_label(stage)} - {len(sessions_with_errors)} sessions with errors")
                stage_layout = QVBoxLayout()
                
                # Create error type summary by CSV filename
                error_types = {}
                for session in sessions_with_errors:
                    for error in session.errors[stage]:
                        # Use error CSV filename as the key
                        error_key = error.get('Error_Query_CSV', 'Unknown Error Query CSV')
                        if error_key not in error_types:
                            error_types[error_key] = []
                        error_types[error_key].append(session)
                
                for error_csv, sessions in error_types.items():
                    error_label = QLabel(f"• {error_csv}: {len(sessions)} session(s)")
                    stage_layout.addWidget(error_label)
                
                stage_group.setLayout(stage_layout)
                scroll_layout.addWidget(stage_group)
        
        scroll_content.setLayout(scroll_layout)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        
        self.content_widget.setLayout(layout)
    
    def show_brainswipes_view(self):
        """Filterable list of sessions by BrainSwipes QC results, exportable as CSV."""
        if self.content_widget.layout():
            QWidget().setLayout(self.content_widget.layout())

        layout = QVBoxLayout()
        title = QLabel("<h2>BrainSwipes QC View</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        has_data = any("BrainSwipes QC" in s.stage_data for s in self.sessions.values())
        if not has_data:
            layout.addWidget(QLabel("No BrainSwipes data loaded. Use Import CSV and choose 'BrainSwipes QC'."))
            self.content_widget.setLayout(layout)
            return

        recons = sorted({r.get("recon") for s in self.sessions.values()
                         for r in s.stage_data.get("BrainSwipes QC", {}).get("recons", [])})

        group = QGroupBox("Filters (check a box to apply a criterion)")
        grid = QGridLayout()
        self.bs_recon = QComboBox()
        self.bs_recon.addItems(["Any"] + recons)
        self.bs_overall = QComboBox()
        self.bs_overall.addItems(["Any", "pass", "fail"])
        self.bs_overall.setCurrentText("pass")
        self.bs_complete = QCheckBox("Only sessions with XCP-D success")
        grid.addWidget(QLabel("Recon:"), 0, 0)
        grid.addWidget(self.bs_recon, 0, 1)
        grid.addWidget(QLabel("Overall:"), 0, 2)
        grid.addWidget(self.bs_overall, 0, 3)
        grid.addWidget(self.bs_complete, 0, 4, 1, 2)

        self.bs_metric_widgets = {}
        for i, (col, label, kind, default) in enumerate(PipelineConfig.BRAINSWIPES_METRICS):
            check = QCheckBox(f"{label} {'≥' if kind == 'min' else '≤'}")
            if isinstance(default, float):
                spin = QDoubleSpinBox()
                spin.setRange(0.0, 1.0)
                spin.setSingleStep(0.05)
            else:
                spin = QSpinBox()
                spin.setRange(0, 999)
            spin.setValue(default)
            self.bs_metric_widgets[col] = (kind, check, spin)
            row, c = 1 + i // 3, (i % 3) * 2
            grid.addWidget(check, row, c)
            grid.addWidget(spin, row, c + 1)
        group.setLayout(grid)
        layout.addWidget(group)

        buttons = QHBoxLayout()
        apply_btn = QPushButton("Apply Filters")
        apply_btn.clicked.connect(self.refresh_brainswipes_results)
        export_btn = QPushButton("Export Matching Sessions")
        export_btn.clicked.connect(self.export_brainswipes_selection)
        buttons.addWidget(apply_btn)
        buttons.addWidget(export_btn)
        self.bs_count = QLabel("")
        buttons.addWidget(self.bs_count)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.bs_table = QTableWidget()
        layout.addWidget(self.bs_table)
        self.content_widget.setLayout(layout)
        self.refresh_brainswipes_results()

    def current_brainswipes_filter(self) -> List[Dict]:
        """Runs the filter using the controls currently shown in the BrainSwipes view."""
        minimums = {c: spin.value() for c, (kind, check, spin) in self.bs_metric_widgets.items()
                    if check.isChecked() and kind == "min"}
        maximums = {c: spin.value() for c, (kind, check, spin) in self.bs_metric_widgets.items()
                    if check.isChecked() and kind == "max"}
        recon = self.bs_recon.currentText()
        overall = self.bs_overall.currentText()
        return filter_brainswipes(
            self.sessions,
            recon=None if recon == "Any" else recon,
            overall=None if overall == "Any" else overall,
            minimums=minimums, maximums=maximums,
            require_complete=self.bs_complete.isChecked())

    def refresh_brainswipes_results(self):
        rows = self.current_brainswipes_filter()
        columns = ["participant_id", "session_id", "recon", "overall"] + \
                  [m[0] for m in PipelineConfig.BRAINSWIPES_METRICS]
        self.bs_table.setColumnCount(len(columns))
        self.bs_table.setHorizontalHeaderLabels(columns)
        self.bs_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, col in enumerate(columns):
                value = row.get(col, "")
                text = "" if pd.isna(value) else (f"{value:.3f}" if isinstance(value, float) else str(value))
                self.bs_table.setItem(r, c, QTableWidgetItem(text))
        self.bs_table.resizeColumnsToContents()
        sessions = {(r["participant_id"], r["session_id"]) for r in rows}
        self.bs_count.setText(f"{len(sessions)} session(s), {len(rows)} recon row(s)")
        self._bs_rows = rows

    def export_brainswipes_selection(self, file_path: str = None):
        """Writes the currently filtered BrainSwipes rows to CSV."""
        rows = self.current_brainswipes_filter()
        if not rows:
            QMessageBox.warning(self, "No Data", "No sessions match the current filters.")
            return
        if not file_path:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Export Matching Sessions", "brainswipes_selected_sessions.csv", "CSV Files (*.csv)")
            if not file_path:
                return
        pd.DataFrame(rows).to_csv(file_path, index=False)
        QMessageBox.information(self, "Success", f"Exported {len(rows)} rows to {file_path}")

    def show_session_details(self, participant_id: str, session_id: str):
        """Shows detailed dialog for a session."""
        session = self.sessions.get((participant_id, session_id))
        if session:
            dialog = SessionDetailDialog(session, self)
            dialog.exec()
    
    def import_csv(self, kind: str = None):
        """Imports one or more CSVs. Files named {stage}__{version}__{audit|errors}[__label].csv
        are routed automatically; any other file prompts for stage, version and type."""
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Import CSV(s)", "", "CSV Files (*.csv)")
        if not file_paths:
            return

        summaries = []
        for file_path in file_paths:
            spec = parse_csv_filename(file_path)
            if spec is None:
                spec = self.ask_import_spec(Path(file_path).name, kind)
                if spec is None:
                    summaries.append(f"{Path(file_path).name}: cancelled")
                    continue
            try:
                report = self.import_file(file_path, spec)
                summaries.append(f"{Path(file_path).name} ({spec['stage']} {spec['version']} "
                                 f"{spec['kind']})\n{report.summary()}")
            except Exception as e:
                summaries.append(f"{Path(file_path).name}: FAILED - {e}")

        self.rebuild_version_controls()
        self.switch_view(self.view_combo.currentText())
        QMessageBox.information(self, "Import summary", "\n\n".join(summaries))

    def import_file(self, file_path: str, spec: Dict[str, str] = None) -> ImportReport:
        """Imports one CSV using its filename schema (or an explicit spec), then refreshes sessions."""
        spec = spec or parse_csv_filename(file_path)
        if spec is None:
            raise ValueError(
                f"'{Path(file_path).name}' does not match {{stage}}__{{version}}__{{audit|errors}}[__label].csv")
        if spec["kind"] == "errors":
            report = self.process_error_csv(file_path, spec["stage"], spec["version"])
        else:
            report = self.process_csv_import(file_path, spec["stage"], spec["version"])
        return report

    def process_csv_import(self, file_path: str, stage: str, version: str = "default") -> ImportReport:
        """Imports an audit/tracking CSV for a stage and pipeline version."""
        report = ImportReport()
        if stage == "MRIQC":
            self._import_mriqc(file_path, version, report)
        elif stage in PipelineConfig.STATUS_STAGES:
            self._import_status_stage(file_path, stage, version, report)
        elif stage == "BrainSwipes QC":
            self._import_brainswipes(file_path, report)
        elif stage == "Notes":
            self._import_notes(file_path, report)
        else:
            raise ValueError(f"Unknown stage: {stage}")
        self.recompute()
        self.warn_unknown_sessions(Path(file_path).name, report)
        return report

    def _read_rows(self, file_path: str, report: ImportReport):
        """Yields (session, row) for rows that match a known session; records the rest in report."""
        df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
        df.columns = df.columns.str.strip()
        self._current_columns = list(df.columns)
        for idx, row in df.iterrows():
            ids = self._extract_ids(row)
            if not ids:
                report.skip("missing participant/session ID", f"row {idx + 2}")
                continue
            session = self.sessions.get(ids)
            if session is None:
                report.skip(ImportReport.UNKNOWN, f"{ids[0]}_{ids[1]}")
                continue
            yield session, row

    def _import_mriqc(self, file_path: str, version: str, report: ImportReport):
        """MRIQC/anatomical-selection CSVs; the table type is detected from its columns."""
        stage = "MRIQC"
        columns = set(pd.read_csv(file_path, nrows=0).columns.str.strip())
        if "best_T1_scan_id" in columns:
            kind = "best"
        elif "fwhm_avg" in columns:
            kind = "metrics"
        elif "t1_count" in columns:
            kind = "counts"
        elif "attempt" in columns:
            kind = "attempts"
        elif {"mode", "bids_run", "dicom_series"} <= columns:
            kind = "series"
        else:
            raise ValueError("Unrecognized MRIQC CSV columns: " + ", ".join(sorted(columns)))

        fields = {
            "best": ["best_T1_scan_id", "best_T2_scan_id"],
            "metrics": ["run", "modality", "fwhm_avg", "snr_total", "snr_gm", "snr_wm"],
            "counts": ["t1_count", "t2_count"],
            "attempts": ["attempt", "n_attempts", "best_t1_run", "best_t2_run", "sheet",
                         "attempt_t1", "attempt_t2"],
        }
        blank = lambda v: str(v).strip() in ("", "NA")

        for session, row in self._read_rows(file_path, report):
            run = session.run(stage, version)
            if kind == "series":
                # Long format: collect unique values per session, keeping leading zeros
                for col in ("mode", "bids_run", "dicom_series"):
                    values = run["data"].setdefault(col, [])
                    value = str(row[col]).strip()
                    if value and value not in values:
                        values.append(value)
            else:
                run["data"].update({c: row.get(c) for c in fields[kind]})
            if kind == "best":
                session.set_status(stage, version, "success")
            elif kind == "counts":
                has_counts = not (blank(row.get("t1_count")) and blank(row.get("t2_count")))
                session.set_status(stage, version, "success" if has_counts else "error")
            report.updated += 1

    def _import_status_stage(self, file_path: str, stage: str, version: str, report: ImportReport):
        """Imports a pending/success/errored tracking CSV for BIBSNet, Nibabies or XCP-D."""
        id_like = {'participant_id', 'Subject_IDs', 'subject_id', 'participant', 'subject', 'sub',
                   'session_id', 'Session_IDs', 'session', 'ses', 'sess'}
        for session, row in self._read_rows(file_path, report):
            session.update_stage_data(stage, version,
                                      {c: row[c] for c in self._current_columns if c not in id_like})
            flag = lambda col: str(row.get(col, '')).strip().upper() == 'TRUE'
            status = "error" if flag('errored') else "success" if flag('success') else "pending"
            session.set_status(stage, version, status)
            report.updated += 1

    def _import_brainswipes(self, file_path: str, report: ImportReport):
        """Imports BrainSwipes results (one row per session and recon).
        Handles the full results sheet and the shorter passable-subjects list; repeated
        imports merge by recon. A session passes if any recon passes."""
        numeric = [m[0] for m in PipelineConfig.BRAINSWIPES_METRICS]
        stage, version = "BrainSwipes QC", PipelineConfig.UNVERSIONED

        for session, row in self._read_rows(file_path, report):
            recon = str(row.get('recon', '')).strip() or 'default'
            entry = {'recon': recon}
            if 'overall' in self._current_columns:
                entry['overall'] = str(row['overall']).strip().lower()
            for col in numeric:
                if col in self._current_columns:
                    entry[col] = pd.to_numeric(row[col], errors='coerce')

            recons = session.run(stage, version)["data"].setdefault("recons", [])
            existing = next((r for r in recons if r['recon'] == recon), None)
            if existing is None:
                entry.setdefault('overall', 'pass')  # passable-subjects lists only contain passes
                recons.append(entry)
            else:
                existing.update(entry)

            passed = any(r.get('overall') == 'pass' for r in recons)
            session.set_status(stage, version, "success" if passed else "error")
            report.updated += 1

    def _import_notes(self, file_path: str, report: ImportReport):
        """Imports per-session free-text notes (columns: participant_id, session_id, notes)."""
        if 'notes' not in pd.read_csv(file_path, nrows=0).columns.str.strip():
            raise ValueError("Notes CSV must contain a 'notes' column")
        for session, row in self._read_rows(file_path, report):
            note = str(row['notes']).strip()
            if note and note not in session.notes:
                session.notes.append(note)
            report.updated += 1

    def process_error_csv(self, file_path: str, stage: str, version: str = "default") -> ImportReport:
        """Associates rows of an error-query CSV with sessions for a stage and pipeline version."""
        report = ImportReport()
        filename = Path(file_path).name
        for session, row in self._read_rows(file_path, report):
            session.add_error(stage, version, {
                'Error_Query_CSV': filename,
                'Run_Number': row.get('Run_Number', 'N/A'),
                'Error_Log_Paths': row.get('Error_Log_Paths', 'N/A')
            })
            report.updated += 1
        self.recompute()
        self.warn_unknown_sessions(filename, report)
        return report

    def ask_import_spec(self, filename: str, kind: str = None) -> Optional[Dict[str, str]]:
        """Asks for stage, version and type of a file that does not follow the naming schema."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Describe {filename}")
        dialog.setMinimumWidth(380)
        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"'{filename}' does not follow<br>"
                                "<code>{stage}__{version}__{audit|errors}[__label].csv</code>"))

        stage_combo = QComboBox()
        stage_combo.addItems(PipelineConfig.VERSIONED_STAGES + PipelineConfig.OVERLAY_STAGES)
        version_edit = QLineEdit()
        version_edit.setPlaceholderText("pipeline version, e.g. 25.0.1")
        kind_combo = QComboBox()
        kind_combo.addItems(["audit", "errors"])
        if kind:
            kind_combo.setCurrentText(kind)
        for label, widget in (("Stage:", stage_combo), ("Version:", version_edit), ("Type:", kind_combo)):
            layout.addWidget(QLabel(label))
            layout.addWidget(widget)

        buttons = QHBoxLayout()
        ok_btn, cancel_btn = QPushButton("OK"), QPushButton("Skip file")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)
        dialog.setLayout(layout)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        stage = stage_combo.currentText()
        version = version_edit.text().strip() or "default"
        if stage in PipelineConfig.OVERLAY_STAGES:
            version = PipelineConfig.UNVERSIONED
        if kind_combo.currentText() == "errors" and stage not in PipelineConfig.VERSIONED_STAGES:
            QMessageBox.warning(self, "Not supported", f"{stage} does not take error CSVs.")
            return None
        return {"stage": stage, "version": version, "kind": kind_combo.currentText(), "label": ""}

    def export_complete_sessions(self):
        """Exports CSV of all sessions that have reached Complete stage."""
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Complete Sessions", 
                                                    "complete_sessions.csv", "CSV Files (*.csv)")
        if not file_path:
            return
        
        try:
            complete_sessions = [s for s in self.sessions.values() if s.current_stage == "Complete"]
            
            if not complete_sessions:
                QMessageBox.warning(self, "No Data", "No sessions have reached the Complete stage yet.")
                return
            
            # Create DataFrame
            data = {
                'participant_id': [s.participant_id for s in complete_sessions],
                'session_id': [s.session_id for s in complete_sessions]
            }
            df = pd.DataFrame(data)
            df.to_csv(file_path, index=False)
            
            QMessageBox.information(self, "Success", 
                                  f"Exported {len(complete_sessions)} complete sessions to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export CSV: {str(e)}")
    

# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(
        description='Neuroimaging Pipeline Tracker GUI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pipeline_tracker.py --input participants.tsv --stages Setup MRIQC BIBSNet Nibabies XCP-D Complete
  python pipeline_tracker.py --input participants.tsv
  
Note: The input file must be a BIDS-compliant participants.tsv file (tab-separated) 
      with 'participant_id' and 'session_id' columns.
        """
    )
    
    parser.add_argument(
        '--input',
        required=True,
        help='Path to BIDS participants.tsv file containing participant_id and session_id columns'
    )
    
    parser.add_argument(
        '--stages',
        nargs='+',
        default=None,
        help='List of pipeline stages to include (default: all stages)'
    )
    
    args = parser.parse_args()
    
    # Validate input file exists
    if not Path(args.input).exists():
        print(f"Error: Input file '{args.input}' does not exist")
        sys.exit(1)
    
    # Validate it's a .tsv file
    if not args.input.endswith('.tsv'):
        print(f"Error: Input file must be a BIDS participants.tsv file (tab-separated values)")
        print(f"Got: {args.input}")
        sys.exit(1)
    
    # Validate stages if provided
    if args.stages:
        invalid_stages = [s for s in args.stages if s not in PipelineConfig.STAGES]
        if invalid_stages:
            print(f"Error: Invalid stages: {invalid_stages}")
            print(f"Valid stages: {PipelineConfig.STAGES}")
            sys.exit(1)
    
    # Create and run application
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    window = PipelineTrackerWindow(args.input, args.stages)
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()


# ============================================================================
# DEVELOPER NOTES
# ============================================================================
"""
MAINTAINER GUIDE:

1. ADDING A NEW STAGE:
   - Add stage name to PipelineConfig.STAGES list
   - Add CSV headers to PipelineConfig.CSV_HEADERS
   - Add stage color to PipelineConfig.STAGE_COLORS
   - Add its token to PipelineConfig.STAGE_TOKENS / VERSIONED_STAGES and a handler in process_csv_import()

2. MODIFYING CSV HEADERS:
   - Update PipelineConfig.CSV_HEADERS for the relevant stage
   - Update the matching _import_* handler to read new columns

3. ADDING NEW MRIQC CSV TYPES:
   - Add new key to PipelineConfig.CSV_HEADERS["MRIQC"]
   - Add a branch to the column detection in _import_mriqc()

4. REMOVING A STAGE:
   - Remove or comment out stage from PipelineConfig.STAGES
   - Optionally remove from CSV_HEADERS and STAGE_COLORS

5. CUSTOMIZING ERROR HANDLING:
   - Modify ERROR_CSV_HEADERS in PipelineConfig
   - Update process_error_csv() to handle different error formats

6. EXTENDING BRAINSWIPES QC:
   - Update apply_brainswipes_threshold() with actual QC logic
   - Modify show_brainswipes_view() for additional statistics
   - Update _import_brainswipes() and PipelineConfig.BRAINSWIPES_METRICS

7. ADDING NEW VIEWS:
   - Add view name to view_combo in setup_ui()
   - Create new show_*_view() method
   - Add case in switch_view() method

ARCHITECTURE:
- SessionData: Core data model for each session
- SessionTile: Visual representation of a session
- SessionDetailDialog: Detailed view of session data
- PipelineTrackerWindow: Main application controller
- PipelineConfig: Centralized configuration

KEY FEATURES:
- Automatic stage advancement when data is imported
- Error tracking per stage per session
- Multiple view modes (Pipeline, Overview, Errors, BrainSwipes)
- Export functionality for completed sessions
- Extensible CSV import system

REQUIREMENTS:
- Python 3.8+
- PyQt6
- pandas
- argparse (standard library)

USAGE:
python pipeline_tracker.py --input participants.tsv --stages Setup MRIQC BIBSNet Complete

Note: The input file MUST be a BIDS-compliant participants.tsv file (tab-separated)
      containing 'participant_id' and 'session_id' columns.
      Example format:
      participant_id    session_id
      sub-001          ses-01
      sub-001          ses-02
      sub-002          ses-01
"""
