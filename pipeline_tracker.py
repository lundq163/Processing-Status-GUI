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
    QComboBox, QSpinBox, QDoubleSpinBox, QTabWidget, QTableWidget,
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
        "BrainSwipes QC",
        "Complete"
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
        "BrainSwipes QC": "#87BCEF",
        "Complete": "#B8E6B8"
    }


# ============================================================================
# DATA MODELS
# ============================================================================

class SessionData:
    """Stores all data for a single session across all pipeline stages."""
    
    def __init__(self, participant_id: str, session_id: str):
        self.participant_id = participant_id
        self.session_id = session_id
        self.current_stage = "Setup"
        self.stage_data = {}  # Dict of stage_name -> data dict
        self.stage_status = {}  # Dict of stage_name -> "success" | "error" | "pending"
        self.errors = {}  # Dict of stage_name -> list of error info
        
    def get_display_name(self) -> str:
        """Returns formatted display name for the session."""
        return f"{self.participant_id}_{self.session_id}"
    
    def update_stage_data(self, stage: str, data: Dict):
        """Updates data for a specific stage."""
        if stage not in self.stage_data:
            self.stage_data[stage] = {}
        self.stage_data[stage].update(data)
    
    def add_error(self, stage: str, error_info: Dict):
        """Adds error information for a specific stage."""
        if stage not in self.errors:
            self.errors[stage] = []
        self.errors[stage].append(error_info)
        self.stage_status[stage] = "error"
    
    def set_stage_success(self, stage: str, advance: bool = False):
        """Marks a stage as successfully completed.
        If advance=True and the session is currently at this stage, move to the next stage.
        Default behavior is to NOT auto-advance to avoid unintended jumps between stages.
        """
        self.stage_status[stage] = "success"
        if advance:
            # Auto-advance to next stage if current stage matches
            stage_idx = PipelineConfig.STAGES.index(stage)
            if stage_idx < len(PipelineConfig.STAGES) - 1:
                next_stage = PipelineConfig.STAGES[stage_idx + 1]
                if self.current_stage == stage:
                    self.current_stage = next_stage


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
        
        # Set background color based on current stage
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
        
        for stage in PipelineConfig.STAGES:
            if stage in self.session.stage_data:
                group = QGroupBox(stage)
                group_layout = QVBoxLayout()
                
                data_text = QTextEdit()
                data_text.setReadOnly(True)
                data_text.setMaximumHeight(150)
                
                # Format stage data
                data_str = ""
                for key, value in self.session.stage_data[stage].items():
                    data_str += f"{key}: {value}\n"
                
                data_text.setText(data_str if data_str else "No data available")
                group_layout.addWidget(data_text)
                
                # Status
                status = self.session.stage_status.get(stage, "pending")
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
        for stage, errors in self.session.errors.items():
            error_content += f"=== {stage} ===\n"
            for idx, error in enumerate(errors, 1):
                error_content += f"\nError {idx}:\n"
                for key, value in error.items():
                    error_content += f"  {key}: {value}\n"
            error_content += "\n"
        
        errors_text.setText(error_content if error_content else "No errors recorded")
        errors_layout.addWidget(errors_text)
        errors_tab.setLayout(errors_layout)
        tabs.addTab(errors_tab, "Errors")
        
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
        self.current_view = "Pipeline"  # "Pipeline" | "Overview" | "Errors" | "BrainSwipes"
        
        # Load initial sessions
        self.load_initial_sessions(initial_csv)
        
        self.setWindowTitle("Processing Stage Tracker")
        self.setMinimumSize(1200, 800)
        self.setup_ui()

    def _promote_session_to_stage(self, session: SessionData, target_stage: str):
        """Promote session to target_stage only if moving forward AND previous stage is not error.
        Always updates data separately; this only controls visual/current stage movement.
        """
        try:
            stages = PipelineConfig.STAGES
            cur_idx = stages.index(session.current_stage)
            tgt_idx = stages.index(target_stage)
            if cur_idx >= tgt_idx:
                return  # no backward moves or same-stage changes here

            # Guard: do not promote if the immediately preceding stage is in error
            if tgt_idx > 0:
                prev_stage = stages[tgt_idx - 1]
                if session.stage_status.get(prev_stage) == "error":
                    return  # blocked by previous stage error

            session.current_stage = target_stage
        except ValueError:
            # Unknown stage name; ignore promotion
            pass
        
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
        import_btn = QPushButton("Import CSV")
        import_btn.clicked.connect(self.import_csv)
        menu_layout.addWidget(import_btn)
        
        import_error_btn = QPushButton("Import Error CSV")
        import_error_btn.clicked.connect(self.import_error_csv)
        menu_layout.addWidget(import_error_btn)
        
        export_btn = QPushButton("Export Complete Sessions")
        export_btn.clicked.connect(self.export_complete_sessions)
        menu_layout.addWidget(export_btn)
        
        main_layout.addLayout(menu_layout)
        
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
        table.setHorizontalHeaderLabels(self.stages)

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
            
            table.setItem(idx, 0, QTableWidgetItem(stage))
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
                stage_group = QGroupBox(f"{stage} - {len(sessions_with_errors)} sessions with errors")
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
        """Shows BrainSwipes QC specific view."""
        if self.content_widget.layout():
            QWidget().setLayout(self.content_widget.layout())
        
        layout = QVBoxLayout()
        
        title = QLabel("<h2>BrainSwipes QC View</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Threshold controls
        threshold_group = QGroupBox("QC Threshold Settings")
        threshold_layout = QHBoxLayout()
        
        threshold_label = QLabel("QC Score Threshold:")
        threshold_layout.addWidget(threshold_label)
        
        threshold_spin = QDoubleSpinBox()
        threshold_spin.setRange(0.0, 1.0)
        threshold_spin.setSingleStep(0.1)
        threshold_spin.setValue(0.7)
        threshold_layout.addWidget(threshold_spin)
        
        apply_btn = QPushButton("Apply Threshold")
        apply_btn.clicked.connect(lambda: self.apply_brainswipes_threshold(threshold_spin.value()))
        threshold_layout.addWidget(apply_btn)
        
        threshold_layout.addStretch()
        threshold_group.setLayout(threshold_layout)
        layout.addWidget(threshold_group)
        
        # BrainSwipes statistics
        stats_text = QTextEdit()
        stats_text.setReadOnly(True)
        stats_text.setMaximumHeight(200)
        
        # Calculate stats
        brainswipes_sessions = [s for s in self.sessions.values() 
                               if s.current_stage == "BrainSwipes QC" or 
                                  "BrainSwipes QC" in s.stage_data]
        
        stats = f"Total sessions in BrainSwipes QC: {len(brainswipes_sessions)}\n"
        stats += f"Sessions passed: {sum(1 for s in brainswipes_sessions if s.stage_status.get('BrainSwipes QC') == 'success')}\n"
        stats += f"Sessions pending: {sum(1 for s in brainswipes_sessions if s.stage_status.get('BrainSwipes QC') == 'pending')}\n"
        
        stats_text.setText(stats)
        layout.addWidget(stats_text)
        
        # Session list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout()
        
        for session in brainswipes_sessions:
            session_label = QLabel(f"{session.get_display_name()} - Status: {session.stage_status.get('BrainSwipes QC', 'pending')}")
            scroll_layout.addWidget(session_label)
        
        scroll_content.setLayout(scroll_layout)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        
        self.content_widget.setLayout(layout)
    
    def apply_brainswipes_threshold(self, threshold: float):
        """Applies QC threshold to BrainSwipes sessions."""
        # MAINTAINERS: Implement logic to evaluate BrainSwipes QC scores against threshold
        # and automatically move passing sessions to Complete stage
        QMessageBox.information(self, "Threshold Applied", 
                              f"Applied threshold of {threshold} to BrainSwipes QC sessions.")
    
    def show_session_details(self, participant_id: str, session_id: str):
        """Shows detailed dialog for a session."""
        session = self.sessions.get((participant_id, session_id))
        if session:
            dialog = SessionDetailDialog(session, self)
            dialog.exec()
    
    def import_csv(self):
        """Imports data from a CSV file."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Import CSV", "", "CSV Files (*.csv)")
        if not file_path:
            return
        
        # Ask user which stage this CSV is for
        stage, ok = self.select_stage_dialog("Select Stage for Import")
        if not ok or not stage:
            return
        
        try:
            self.process_csv_import(file_path, stage)
            QMessageBox.information(self, "Success", f"Successfully imported data for {stage} stage")
            self.show_pipeline_view()  # Refresh view
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import CSV: {str(e)}")
    
    def process_csv_import(self, file_path: str, stage: str):
        """Processes CSV import for a specific stage."""
        df = pd.read_csv(file_path)
        df.columns = df.columns.str.strip()
        
        # MAINTAINERS: Add stage-specific processing logic here
        
        if stage == "MRIQC":
            # Determine which MRIQC CSV type this is
            if "best_T1_scan_id" in df.columns:
                # Best anatomical CSV
                for _, row in df.iterrows():
                    pid = str(row['participant_id']).strip()
                    sid = str(row['session_id']).strip()
                    key = (pid, sid)
                    
                    if key in self.sessions:
                        data = {
                            'best_T1_scan_id': row.get('best_T1_scan_id'),
                            'best_T2_scan_id': row.get('best_T2_scan_id')
                        }
                        self.sessions[key].update_stage_data(stage, data)
                        # Mark MRIQC data present; consider this step successful for best anatomical selection
                        self.sessions[key].set_stage_success(stage)
                        # Ensure the session shows under MRIQC (do this AFTER set_stage_success
                        # to avoid auto-advance when current_stage equals the target stage)
                        self._promote_session_to_stage(self.sessions[key], stage)
            
            elif "fwhm_avg" in df.columns:
                # Quality metrics CSV
                for _, row in df.iterrows():
                    pid = str(row['participant_id']).strip()
                    sid = str(row['session_id']).strip()
                    key = (pid, sid)
                    
                    if key in self.sessions:
                        data = {
                            'run': row.get('run'),
                            'modality': row.get('modality'),
                            'fwhm_avg': row.get('fwhm_avg'),
                            'snr_total': row.get('snr_total'),
                            'snr_gm': row.get('snr_gm'),
                            'snr_wm': row.get('snr_wm')
                        }
                        self.sessions[key].update_stage_data(stage, data)
                        # Ensure it appears under MRIQC even if Setup hasn't been marked complete
                        self._promote_session_to_stage(self.sessions[key], stage)
                        
            elif "t1_count" in df.columns:
                # bcp_bids_anat_counts.csv - mark success if t1_count or t2_count present, else error
                for _, row in df.iterrows():
                    pid = str(row['participant_id']).strip()
                    sid = str(row['session_id']).strip()
                    key = (pid, sid)
                    
                    if key in self.sessions:
                        t1_count = row.get('t1_count')
                        t2_count = row.get('t2_count')
                        
                        data = {
                            't1_count': t1_count,
                            't2_count': t2_count
                        }
                        self.sessions[key].update_stage_data(stage, data)
                        
                        # Mark success if either t1_count or t2_count has data
                        if pd.notna(t1_count) and str(t1_count).strip() != '' or \
                           pd.notna(t2_count) and str(t2_count).strip() != '':
                            self.sessions[key].set_stage_success(stage)
                        else:
                            # Mark as error if no count data
                            self.sessions[key].stage_status[stage] = "error"
                        
                        # Ensure it appears under MRIQC even if Setup hasn't been marked complete
                        self._promote_session_to_stage(self.sessions[key], stage)
                        
            elif "attempt" in df.columns:
                # bcp_bids_anat_counts.csv
                for _, row in df.iterrows():
                    pid = str(row['participant_id']).strip()
                    sid = str(row['session_id']).strip()
                    key = (pid, sid)
                    
                    if key in self.sessions:
                        data = {
                            'attempt': row.get('attempt'),
                            'n_attempts': row.get('n_attempts'),
                            'best_t1_run': row.get('best_t1_run'),
                            'best_t2_run': row.get('best_t2_run'),
                            'sheet': row.get('sheet'),
                            'attempt_t1': row.get('attempt_t1'),
                            'attempt_t2': row.get('attempt_t2')
                        }
                        self.sessions[key].update_stage_data(stage, data)
                        # Ensure it appears under MRIQC even if Setup hasn't been marked complete
                        self._promote_session_to_stage(self.sessions[key], stage)

            elif {"mode", "bids_run", "dicom_series"}.issubset(set(df.columns)):
                # series_run_key_output.csv (long format): aggregate values into lists per session
                # Re-read this file with strings preserved to avoid losing leading zeros
                df_series = pd.read_csv(file_path, dtype=str, keep_default_na=False)
                df_series.columns = df_series.columns.str.strip()
                for (pid, sid), group in df_series.groupby(["participant_id", "session_id"], dropna=False):
                    pid = str(pid).strip()
                    sid = str(sid).strip()
                    key = (pid, sid)
                    if key not in self.sessions:
                        continue

                    def dedup_preserve_order(seq):
                        seen = set()
                        out = []
                        for v in seq:
                            if v not in seen:
                                seen.add(v)
                                out.append(v)
                        return out

                    # Preserve original string values as-is (no padding/formatting changes)
                    modes = dedup_preserve_order([str(v).strip() for v in group["mode"].tolist() if str(v).strip() != ""])
                    bids_runs = dedup_preserve_order([str(v).strip() for v in group["bids_run"].tolist() if str(v).strip() != ""])
                    dicom_series = dedup_preserve_order([str(v).strip() for v in group["dicom_series"].tolist() if str(v).strip() != ""])

                    # Merge with any existing data for this stage
                    existing = self.sessions[key].stage_data.get(stage, {})

                    def merge_list(existing_value, new_list):
                        if isinstance(existing_value, list):
                            base = existing_value[:]
                        elif existing_value is None:
                            base = []
                        else:
                            base = [existing_value]
                        # extend with items not already present (preserve order)
                        for item in new_list:
                            if item not in base:
                                base.append(item)
                        return base

                    data = {
                        "mode": merge_list(existing.get("mode"), modes),
                        "bids_run": merge_list(existing.get("bids_run"), bids_runs),
                        "dicom_series": merge_list(existing.get("dicom_series"), dicom_series),
                    }

                    self.sessions[key].update_stage_data(stage, data)
                    # Keep session positioned under the selected stage
                    self._promote_session_to_stage(self.sessions[key], stage)
            
            # MAINTAINERS: Add additional MRIQC CSV processing here
            # elif "other_column" in df.columns:
            #     # Process other MRIQC CSV type
        
        elif stage == "BIBSNet":
            # BIBSNet CSV processing: only move sessions with MRIQC success status
            # Re-read with dtype=str to preserve leading zeros in participant IDs
            df_bibsnet = pd.read_csv(file_path, dtype=str, keep_default_na=False)
            df_bibsnet.columns = df_bibsnet.columns.str.strip()
            
            updated = 0
            print(f"[DEBUG] BIBSNet import: Total rows in CSV = {len(df_bibsnet)}")
            print(f"[DEBUG] BIBSNet import: CSV columns = {df_bibsnet.columns.tolist()}")
            for _, row in df_bibsnet.iterrows():
                ids = self._extract_ids(row)
                if not ids:
                    continue
                pid, sid = ids
                key = (pid, sid)
                if key not in self.sessions:
                    continue
                
                # Only move to BIBSNet if MRIQC stage has success status
                mriqc_status = self.sessions[key].stage_status.get("MRIQC")
                if mriqc_status != "success":
                    print(f"[DEBUG] BIBSNet import: Skipping {key} - MRIQC status is '{mriqc_status}' (not 'success')")
                    continue
                
                # Exclude any ID-like columns when copying data
                id_like = {'participant_id', 'Subject_IDs', 'subject_id', 'participant', 'subject', 'sub',
                           'session_id', 'Session_IDs', 'session', 'ses', 'sess'}
                data = {col: row[col] for col in df_bibsnet.columns if col not in id_like}
                self.sessions[key].update_stage_data(stage, data)
                
                # Determine status based on success/errored/pending columns
                success_val = str(row.get('success', '')).strip().upper()
                errored_val = str(row.get('errored', '')).strip().upper()
                pending_val = str(row.get('pending', '')).strip().upper()
                
                if errored_val == 'TRUE':
                    self.sessions[key].stage_status[stage] = "error"
                    print(f"[DEBUG] BIBSNet: {key} marked as ERROR (errored=TRUE)")
                elif success_val == 'TRUE':
                    self.sessions[key].set_stage_success(stage)
                    print(f"[DEBUG] BIBSNet: {key} marked as SUCCESS (success=TRUE)")
                elif pending_val == 'TRUE':
                    self.sessions[key].stage_status[stage] = "pending"
                    print(f"[DEBUG] BIBSNet: {key} marked as PENDING (pending=TRUE)")
                else:
                    # Default to pending if no status info
                    self.sessions[key].stage_status[stage] = "pending"
                
                self._promote_session_to_stage(self.sessions[key], stage)
                updated += 1
            
            print(f"[INFO] BIBSNet import: Updated {updated} sessions.")
        
        elif stage == "Nibabies":
            # Nibabies CSV processing: only move sessions with BIBSNet success status
            # Re-read with dtype=str to preserve leading zeros in participant IDs
            df_nibabies = pd.read_csv(file_path, dtype=str, keep_default_na=False)
            df_nibabies.columns = df_nibabies.columns.str.strip()
            
            updated = 0
            for _, row in df_nibabies.iterrows():
                ids = self._extract_ids(row)
                if not ids:
                    continue
                pid, sid = ids
                key = (pid, sid)
                if key not in self.sessions:
                    continue
                
                # Only move to Nibabies if BIBSNet stage has success status
                bibsnet_status = self.sessions[key].stage_status.get("BIBSNet")
                if bibsnet_status != "success":
                    print(f"[DEBUG] Nibabies import: Skipping {key} - BIBSNet status is '{bibsnet_status}' (not 'success')")
                    continue
                
                id_like = {'participant_id', 'Subject_IDs', 'subject_id', 'participant', 'subject', 'sub',
                           'session_id', 'Session_IDs', 'session', 'ses', 'sess'}
                data = {col: row[col] for col in df_nibabies.columns if col not in id_like}
                self.sessions[key].update_stage_data(stage, data)
                
                # Determine status based on success/errored/pending columns
                success_val = str(row.get('success', '')).strip().upper()
                errored_val = str(row.get('errored', '')).strip().upper()
                pending_val = str(row.get('pending', '')).strip().upper()
                
                if errored_val == 'TRUE':
                    self.sessions[key].stage_status[stage] = "error"
                    print(f"[DEBUG] Nibabies: {key} marked as ERROR (errored=TRUE)")
                elif success_val == 'TRUE':
                    self.sessions[key].set_stage_success(stage)
                    print(f"[DEBUG] Nibabies: {key} marked as SUCCESS (success=TRUE)")
                elif pending_val == 'TRUE':
                    self.sessions[key].stage_status[stage] = "pending"
                    print(f"[DEBUG] Nibabies: {key} marked as PENDING (pending=TRUE)")
                else:
                    # Default to pending if no status info
                    self.sessions[key].stage_status[stage] = "pending"
                
                self._promote_session_to_stage(self.sessions[key], stage)
                updated += 1
            
            print(f"[INFO] Nibabies import: Updated {updated} sessions.")
        
        elif stage == "XCP-D":
            # XCP-D CSV processing: only move sessions with Nibabies success status
            # Re-read with dtype=str to preserve leading zeros in participant IDs
            df_xcpd = pd.read_csv(file_path, dtype=str, keep_default_na=False)
            df_xcpd.columns = df_xcpd.columns.str.strip()
            
            updated = 0
            for _, row in df_xcpd.iterrows():
                ids = self._extract_ids(row)
                if not ids:
                    continue
                pid, sid = ids
                key = (pid, sid)
                if key not in self.sessions:
                    continue
                
                # Only move to XCP-D if Nibabies stage has success status
                nibabies_status = self.sessions[key].stage_status.get("Nibabies")
                if nibabies_status != "success":
                    print(f"[DEBUG] XCP-D import: Skipping {key} - Nibabies status is '{nibabies_status}' (not 'success')")
                    continue
                
                id_like = {'participant_id', 'Subject_IDs', 'subject_id', 'participant', 'subject', 'sub',
                           'session_id', 'Session_IDs', 'session', 'ses', 'sess'}
                data = {col: row[col] for col in df_xcpd.columns if col not in id_like}
                self.sessions[key].update_stage_data(stage, data)
                
                # Determine status based on success/errored/pending columns
                success_val = str(row.get('success', '')).strip().upper()
                errored_val = str(row.get('errored', '')).strip().upper()
                pending_val = str(row.get('pending', '')).strip().upper()
                
                if errored_val == 'TRUE':
                    self.sessions[key].stage_status[stage] = "error"
                    print(f"[DEBUG] XCP-D: {key} marked as ERROR (errored=TRUE)")
                elif success_val == 'TRUE':
                    self.sessions[key].set_stage_success(stage)
                    print(f"[DEBUG] XCP-D: {key} marked as SUCCESS (success=TRUE)")
                elif pending_val == 'TRUE':
                    self.sessions[key].stage_status[stage] = "pending"
                    print(f"[DEBUG] XCP-D: {key} marked as PENDING (pending=TRUE)")
                else:
                    # Default to pending if no status info
                    self.sessions[key].stage_status[stage] = "pending"
                
                self._promote_session_to_stage(self.sessions[key], stage)
                updated += 1
            
            print(f"[INFO] XCP-D import: Updated {updated} sessions.")
        
        elif stage == "BrainSwipes QC":
            # MAINTAINERS: Implement BrainSwipes QC CSV processing
            # Expected columns should include QC pass/fail status
            for _, row in df.iterrows():
                pid = str(row['participant_id']).strip()
                sid = str(row['session_id']).strip()
                key = (pid, sid)
                
                if key in self.sessions:
                    data = {col: row[col] for col in df.columns if col not in ['participant_id', 'session_id']}
                    self.sessions[key].update_stage_data(stage, data)
                    
                    # Check if session passes QC (adjust column name as needed)
                    # MAINTAINERS: Update 'qc_pass' to match actual column name
                    if 'qc_pass' in row and row['qc_pass']:
                        self.sessions[key].set_stage_success(stage)
                        # Auto-advance to Complete stage
                        self.sessions[key].current_stage = "Complete"
                    else:
                        # If not passed yet, ensure it at least appears under BrainSwipes QC
                        self._promote_session_to_stage(self.sessions[key], stage)
    
    def import_error_csv(self):
        """Imports error query CSV and associates errors with sessions."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Import Error CSV", "", "CSV Files (*.csv)")
        if not file_path:
            return
        
        # Ask user which stage these errors belong to
        stage, ok = self.select_stage_dialog("Select Stage for Errors")
        if not ok or not stage:
            return
        
        try:
            # Extract the filename from the path
            import os
            filename = os.path.basename(file_path)
            
            df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
            df.columns = df.columns.str.strip()
            
            updated = 0
            # Process error CSV
            for _, row in df.iterrows():
                # Handle different possible column name formats
                pid = None
                sid = None
                
                if 'Subject_IDs' in df.columns:
                    pid = str(row['Subject_IDs']).strip()
                elif 'participant_id' in df.columns:
                    pid = str(row['participant_id']).strip()
                
                if 'Session_IDs' in df.columns:
                    sid = str(row['Session_IDs']).strip()
                elif 'session_id' in df.columns:
                    sid = str(row['session_id']).strip()
                
                if pid and sid:
                    # Normalize to BIDS format if not already
                    if not pid.startswith('sub-'):
                        pid = f'sub-{pid}'
                    if not sid.startswith('ses-'):
                        sid = f'ses-{sid}'
                    
                    key = (pid, sid)
                    if key in self.sessions:
                        error_info = {
                            'Error_Query_CSV': filename,
                            'Run_Number': row.get('Run_Number', 'N/A'),
                            'Error_Log_Paths': row.get('Error_Log_Paths', 'N/A')
                        }
                        self.sessions[key].add_error(stage, error_info)
                        # Revert session to the error stage and mark with error status
                        self.sessions[key].current_stage = stage
                        self.sessions[key].stage_status[stage] = "error"
                        updated += 1
            
            QMessageBox.information(self, "Success", f"Successfully imported {updated} errors for {stage} stage")
            self.show_pipeline_view()  # Refresh view
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import error CSV: {str(e)}")
    
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
    
    def select_stage_dialog(self, title: str) -> tuple:
        """Shows dialog to select a stage."""
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumWidth(300)
        
        layout = QVBoxLayout()
        
        label = QLabel("Select stage:")
        layout.addWidget(label)
        
        combo = QComboBox()
        # Exclude Setup and Complete stages for data import
        import_stages = [s for s in self.stages if s not in ["Setup", "Complete"]]
        combo.addItems(import_stages)
        layout.addWidget(combo)
        
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        
        result = dialog.exec()
        return combo.currentText(), result == QDialog.DialogCode.Accepted


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
  python pipeline_tracker.py --input participants.tsv --stages Setup MRIQC BIBSNet Nibabies XCP-D "BrainSwipes QC" Complete
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
   - Add processing logic in process_csv_import() method

2. MODIFYING CSV HEADERS:
   - Update PipelineConfig.CSV_HEADERS for the relevant stage
   - Update processing logic in process_csv_import() to handle new columns

3. ADDING NEW MRIQC CSV TYPES:
   - Add new key to PipelineConfig.CSV_HEADERS["MRIQC"]
   - Add elif block in process_csv_import() under MRIQC section

4. REMOVING A STAGE:
   - Remove or comment out stage from PipelineConfig.STAGES
   - Optionally remove from CSV_HEADERS and STAGE_COLORS

5. CUSTOMIZING ERROR HANDLING:
   - Modify ERROR_CSV_HEADERS in PipelineConfig
   - Update import_error_csv() method to handle different error formats

6. EXTENDING BRAINSWIPES QC:
   - Update apply_brainswipes_threshold() with actual QC logic
   - Modify show_brainswipes_view() for additional statistics
   - Update BrainSwipes QC processing in process_csv_import()

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
