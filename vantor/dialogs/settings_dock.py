"""
Settings Dock Widget for Vantor Plugin

Provides a settings panel with dependency management
and general configuration options.
"""

from qgis.PyQt.QtCore import Qt, QSettings, QTimer
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QGroupBox,
    QFormLayout,
    QMessageBox,
    QFileDialog,
    QTabWidget,
    QProgressBar,
)
from qgis.PyQt.QtGui import QFont


class SettingsDockWidget(QDockWidget):
    """A settings panel for configuring Vantor plugin options."""

    SETTINGS_PREFIX = "Vantor/"

    def __init__(self, iface, parent=None):
        """Initialize the settings dock widget.

        Args:
            iface: QGIS interface instance.
            parent: Parent widget.
        """
        super().__init__("Vantor Settings", parent)
        self.iface = iface
        self.settings = QSettings()

        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        """Set up the settings UI."""
        main_widget = QWidget()
        self.setWidget(main_widget)

        layout = QVBoxLayout(main_widget)
        layout.setSpacing(10)

        # Header
        header_label = QLabel("Settings")
        header_font = QFont()
        header_font.setPointSize(12)
        header_font.setBold(True)
        header_label.setFont(header_font)
        header_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(header_label)

        # Tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Dependencies tab
        dependencies_tab = self._create_dependencies_tab()
        self.tab_widget.addTab(dependencies_tab, "Dependencies")

        # General tab
        general_tab = self._create_general_tab()
        self.tab_widget.addTab(general_tab, "General")

        # Buttons
        button_layout = QHBoxLayout()

        self.save_btn = QPushButton("Save Settings")
        self.save_btn.clicked.connect(self._save_settings)
        button_layout.addWidget(self.save_btn)

        self.reset_btn = QPushButton("Reset Defaults")
        self.reset_btn.clicked.connect(self._reset_defaults)
        button_layout.addWidget(self.reset_btn)

        layout.addLayout(button_layout)

        layout.addStretch()

        # Status label
        self.status_label = QLabel("Settings loaded")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

    def _create_dependencies_tab(self):
        """Create the dependencies management tab."""
        from ..deps_manager import REQUIRED_PACKAGES

        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Info label
        info_label = QLabel(
            "This plugin requires the following Python packages.\n"
            "Click 'Install Dependencies' to install them in an isolated\n"
            "virtual environment that does not affect your QGIS Python."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("font-size: 10px; padding: 5px;")
        layout.addWidget(info_label)

        # Dependencies status group
        deps_group = QGroupBox("Package Status")
        deps_layout = QVBoxLayout(deps_group)

        self.dep_status_labels = {}
        for import_name, pip_name in REQUIRED_PACKAGES:
            row_layout = QHBoxLayout()
            name_label = QLabel(f"  {pip_name}")
            name_label.setMinimumWidth(100)
            status_label = QLabel("Checking...")
            status_label.setStyleSheet("color: gray;")
            row_layout.addWidget(name_label)
            row_layout.addWidget(status_label)
            row_layout.addStretch()
            deps_layout.addLayout(row_layout)
            self.dep_status_labels[import_name] = status_label

        layout.addWidget(deps_group)

        # Overall status
        self.deps_overall_label = QLabel("Checking dependencies...")
        self.deps_overall_label.setWordWrap(True)
        self.deps_overall_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(self.deps_overall_label)

        # Progress bar (hidden by default)
        self.deps_progress_bar = QProgressBar()
        self.deps_progress_bar.setRange(0, 100)
        self.deps_progress_bar.setVisible(False)
        layout.addWidget(self.deps_progress_bar)

        # Progress label (hidden by default)
        self.deps_progress_label = QLabel("")
        self.deps_progress_label.setWordWrap(True)
        self.deps_progress_label.setStyleSheet("font-size: 10px;")
        self.deps_progress_label.setVisible(False)
        layout.addWidget(self.deps_progress_label)

        # Install button
        self.install_deps_btn = QPushButton("Install Dependencies")
        self.install_deps_btn.setStyleSheet("""
            QPushButton {
                background-color: #1976D2;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #1565C0; }
            QPushButton:disabled { background-color: #BDBDBD; }
        """)
        self.install_deps_btn.clicked.connect(self._install_dependencies)
        layout.addWidget(self.install_deps_btn)

        # Refresh button
        self.refresh_deps_btn = QPushButton("Refresh Status")
        self.refresh_deps_btn.clicked.connect(self._refresh_dependency_status)
        layout.addWidget(self.refresh_deps_btn)

        layout.addStretch()

        # Note about isolation
        note_label = QLabel(
            "Packages are installed in an isolated environment\n"
            "(~/.qgis_vantor/) and do not affect your QGIS Python.\n"
            "If packages are not detected after installation, restart QGIS."
        )
        note_label.setWordWrap(True)
        note_label.setStyleSheet("font-size: 9px; font-style: italic;")
        layout.addWidget(note_label)

        QTimer.singleShot(100, self._refresh_dependency_status)

        return widget

    def _refresh_dependency_status(self):
        """Check and display the status of all required dependencies."""
        from ..deps_manager import check_dependencies

        deps = check_dependencies()
        all_ok = True

        for dep in deps:
            label = self.dep_status_labels.get(dep["name"])
            if label is None:
                continue
            if dep["installed"]:
                version_str = dep["version"] or "installed"
                label.setText(f"Installed ({version_str})")
                label.setStyleSheet("color: green; font-weight: bold;")
            else:
                label.setText("Not installed")
                label.setStyleSheet("color: red;")
                all_ok = False

        if all_ok:
            self.deps_overall_label.setText("All dependencies are installed.")
            self.deps_overall_label.setStyleSheet(
                "color: green; font-weight: bold; padding: 5px;"
            )
            self.install_deps_btn.setVisible(False)
        else:
            missing_count = sum(1 for d in deps if not d["installed"])
            self.deps_overall_label.setText(
                f"{missing_count} package(s) missing. "
                "Click 'Install Dependencies' to install."
            )
            self.deps_overall_label.setStyleSheet(
                "color: #E65100; font-weight: bold; padding: 5px;"
            )
            self.install_deps_btn.setVisible(True)
            self.install_deps_btn.setEnabled(True)

    def _install_dependencies(self):
        """Start installing missing dependencies in a background thread."""
        from ..deps_manager import DepsInstallWorker

        self.install_deps_btn.setEnabled(False)
        self.install_deps_btn.setText("Installing...")
        self.refresh_deps_btn.setEnabled(False)

        self.deps_progress_bar.setVisible(True)
        self.deps_progress_bar.setValue(0)
        self.deps_progress_label.setVisible(True)
        self.deps_progress_label.setText("Starting installation...")

        self._deps_worker = DepsInstallWorker()
        self._deps_worker.progress.connect(self._on_deps_install_progress)
        self._deps_worker.finished.connect(self._on_deps_install_finished)
        self._deps_worker.start()

    def _on_deps_install_progress(self, percent, message):
        """Handle progress updates from the install worker.

        Args:
            percent: Installation progress percentage (0-100).
            message: Status message to display.
        """
        self.deps_progress_bar.setValue(percent)
        self.deps_progress_label.setText(message)

    def _on_deps_install_finished(self, success, message):
        """Handle completion of dependency installation.

        Args:
            success: Whether installation was successful.
            message: Result message.
        """
        self.deps_progress_bar.setVisible(False)
        self.deps_progress_label.setVisible(False)
        self.install_deps_btn.setText("Install Dependencies")
        self.refresh_deps_btn.setEnabled(True)

        if success:
            self.deps_overall_label.setText(message)
            self.deps_overall_label.setStyleSheet(
                "color: green; font-weight: bold; padding: 5px;"
            )
            self.iface.messageBar().pushSuccess(
                "Vantor", "Dependencies installed successfully!"
            )
            self._refresh_dependency_status()

            QMessageBox.information(
                self,
                "Dependencies Installed",
                "Dependencies have been installed successfully.\n\n"
                "If the plugin does not work immediately, "
                "please restart QGIS.",
            )
        else:
            self.deps_overall_label.setText("Installation failed.")
            self.deps_overall_label.setStyleSheet(
                "color: red; font-weight: bold; padding: 5px;"
            )
            self.install_deps_btn.setEnabled(True)

            QMessageBox.critical(
                self,
                "Installation Failed",
                f"Failed to install dependencies:\n\n{message}\n\n"
                "You can try installing manually with:\n"
                "pip install pystac",
            )

        self._deps_worker = None

    def show_dependencies_tab(self):
        """Switch to the Dependencies tab programmatically."""
        self.tab_widget.setCurrentIndex(0)

    def _create_general_tab(self):
        """Create the general settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Download settings group
        download_group = QGroupBox("Download")
        download_layout = QFormLayout(download_group)

        # Default download directory
        dir_layout = QHBoxLayout()
        self.download_dir_input = QLineEdit()
        self.download_dir_input.setPlaceholderText("Default download directory...")
        dir_layout.addWidget(self.download_dir_input)
        self.download_dir_btn = QPushButton("...")
        self.download_dir_btn.setMaximumWidth(30)
        self.download_dir_btn.clicked.connect(self._browse_download_dir)
        dir_layout.addWidget(self.download_dir_btn)
        download_layout.addRow("Download directory:", dir_layout)

        layout.addWidget(download_group)

        layout.addStretch()
        return widget

    def _browse_download_dir(self):
        """Open directory browser for download path."""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Download Directory", self.download_dir_input.text() or ""
        )
        if dir_path:
            self.download_dir_input.setText(dir_path)

    def _load_settings(self):
        """Load settings from QSettings."""
        self.download_dir_input.setText(
            self.settings.value(f"{self.SETTINGS_PREFIX}download_dir", "", type=str)
        )
        self.status_label.setText("Settings loaded")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")

    def _save_settings(self):
        """Save settings to QSettings."""
        self.settings.setValue(
            f"{self.SETTINGS_PREFIX}download_dir",
            self.download_dir_input.text(),
        )
        self.settings.sync()

        self.status_label.setText("Settings saved")
        self.status_label.setStyleSheet("color: green; font-size: 10px;")
        self.iface.messageBar().pushSuccess("Vantor", "Settings saved successfully!")

    def _reset_defaults(self):
        """Reset all settings to defaults."""
        reply = QMessageBox.question(
            self,
            "Reset Settings",
            "Are you sure you want to reset all settings to defaults?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        self.download_dir_input.clear()
        self.status_label.setText("Defaults restored (not saved)")
        self.status_label.setStyleSheet("color: orange; font-size: 10px;")
