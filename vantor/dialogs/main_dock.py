"""
Main Dock Widget for Vantor Plugin

Provides the primary UI for searching, browsing, visualizing,
and downloading Vantor STAC catalog data.
"""

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QCheckBox,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QFileDialog,
    QMessageBox,
    QProgressBar,
)
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsRasterLayer,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
)
from ..workers import CatalogFetchWorker, ItemsFetchWorker, DownloadWorker
from ..map_tools import BBoxMapTool, FootprintHighlighter
from .. import stac_client


class VantorMainDock(QDockWidget):
    """Main dock widget for Vantor STAC catalog browsing."""

    def __init__(self, iface, parent=None):
        """Initialize the main dock widget.

        Args:
            iface: QGIS interface instance.
            parent: Parent widget.
        """
        super().__init__("Vantor", parent)
        self.iface = iface
        self.canvas = iface.mapCanvas()

        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        # State
        self._events = []
        self._items = []
        self._footprint_layer = None
        self._bbox_tool = None
        self._drawn_bbox = None
        self._previous_map_tool = None
        self._catalog_worker = None
        self._items_worker = None
        self._download_worker = None
        self._highlighter = FootprintHighlighter(self.canvas)
        self._updating_selection = False

        self._setup_ui()

        # Fetch catalog events after UI is ready
        QTimer.singleShot(200, self._fetch_events)

    def _setup_ui(self):
        """Set up the dock widget UI."""
        main_widget = QWidget()
        self.setWidget(main_widget)

        layout = QVBoxLayout(main_widget)
        layout.setSpacing(8)

        # Header
        header_label = QLabel("Vantor STAC Browser")
        header_font = QFont()
        header_font.setPointSize(11)
        header_font.setBold(True)
        header_label.setFont(header_font)
        header_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(header_label)

        # Search section
        search_group = QGroupBox("Search")
        search_layout = QVBoxLayout(search_group)

        # Event selector row
        event_row = QHBoxLayout()
        event_row.addWidget(QLabel("Event:"))
        self.event_combo = QComboBox()
        self.event_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLength)
        self.event_combo.setMinimumContentsLength(20)
        event_row.addWidget(self.event_combo, 1)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setMaximumWidth(70)
        self.refresh_btn.setToolTip("Re-fetch catalog to discover new events")
        self.refresh_btn.clicked.connect(self._fetch_events)
        event_row.addWidget(self.refresh_btn)
        search_layout.addLayout(event_row)

        # Phase filter row
        phase_row = QHBoxLayout()
        phase_row.addWidget(QLabel("Phase:"))
        self.phase_combo = QComboBox()
        self.phase_combo.addItems(["All", "Pre-event", "Post-event"])
        phase_row.addWidget(self.phase_combo, 1)
        search_layout.addLayout(phase_row)

        # Spatial filter row
        spatial_row = QHBoxLayout()
        self.use_extent_check = QCheckBox("Use Map Extent")
        self.use_extent_check.setToolTip(
            "Filter results to the current map view extent"
        )
        spatial_row.addWidget(self.use_extent_check)

        self.draw_bbox_btn = QPushButton("Draw BBox")
        self.draw_bbox_btn.setToolTip(
            "Draw a bounding box on the map to filter results"
        )
        self.draw_bbox_btn.setCheckable(True)
        self.draw_bbox_btn.clicked.connect(self._toggle_bbox_tool)
        spatial_row.addWidget(self.draw_bbox_btn)

        self.clear_bbox_btn = QPushButton("Clear")
        self.clear_bbox_btn.setMaximumWidth(50)
        self.clear_bbox_btn.setToolTip("Clear the drawn bounding box")
        self.clear_bbox_btn.clicked.connect(self._clear_bbox)
        self.clear_bbox_btn.setEnabled(False)
        spatial_row.addWidget(self.clear_bbox_btn)
        search_layout.addLayout(spatial_row)

        # Bbox info label
        self.bbox_label = QLabel("")
        self.bbox_label.setStyleSheet("color: gray; font-size: 9px;")
        self.bbox_label.setWordWrap(True)
        search_layout.addWidget(self.bbox_label)

        # Search button
        self.search_btn = QPushButton("Search")
        self.search_btn.setStyleSheet("""
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
        self.search_btn.clicked.connect(self._search)
        search_layout.addWidget(self.search_btn)

        layout.addWidget(search_group)

        # Results section
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout(results_group)

        self.results_label = QLabel("No results")
        self.results_label.setStyleSheet("color: #a0a0a0; font-size: 10px;")
        results_layout.addWidget(self.results_label)

        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(7)
        self.results_table.setHorizontalHeaderLabels(
            ["", "ID", "Date", "Phase", "Sensor", "Cloud%", "GSD (m)"]
        )
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for col in range(2, 7):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
            header.resizeSection(col, 80)
        self.results_table.setSortingEnabled(True)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.currentCellChanged.connect(self._on_table_selection_changed)
        results_layout.addWidget(self.results_table)

        # Selection buttons
        sel_row = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self._select_all)
        sel_row.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        sel_row.addWidget(self.deselect_all_btn)
        results_layout.addLayout(sel_row)

        layout.addWidget(results_group)

        # Action buttons
        action_row = QHBoxLayout()

        self.visualize_btn = QPushButton("Visualize")
        self.visualize_btn.setToolTip("Add selected items as COG raster layers")
        self.visualize_btn.setStyleSheet("""
            QPushButton {
                background-color: #388E3C;
                color: white;
                font-weight: bold;
                padding: 5px 10px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #2E7D32; }
            QPushButton:disabled { background-color: #BDBDBD; }
        """)
        self.visualize_btn.clicked.connect(self._visualize_selected)
        action_row.addWidget(self.visualize_btn)

        self.download_btn = QPushButton("Download")
        self.download_btn.setToolTip("Download selected COG files to disk")
        self.download_btn.setStyleSheet("""
            QPushButton {
                background-color: #F57C00;
                color: white;
                font-weight: bold;
                padding: 5px 10px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #EF6C00; }
            QPushButton:disabled { background-color: #BDBDBD; }
        """)
        self.download_btn.clicked.connect(self._download_selected)
        action_row.addWidget(self.download_btn)

        layout.addLayout(action_row)

        # Progress bar with cancel button
        progress_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_row.addWidget(self.progress_bar)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMaximumWidth(60)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_download)
        progress_row.addWidget(self.cancel_btn)
        layout.addLayout(progress_row)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #a0a0a0; font-size: 10px;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def _fetch_events(self):
        """Fetch catalog events from S3 in background."""
        self.status_label.setText("Fetching catalog...")
        self.status_label.setStyleSheet("color: #5cabff; font-size: 10px;")
        self.refresh_btn.setEnabled(False)
        self.search_btn.setEnabled(False)

        self._catalog_worker = CatalogFetchWorker()
        self._catalog_worker.finished.connect(self._on_events_fetched)
        self._catalog_worker.error.connect(self._on_events_error)
        self._catalog_worker.start()

    def _on_events_fetched(self, events):
        """Handle successfully fetched events.

        Args:
            events: List of event dicts from the catalog.
        """
        self._events = events
        self.event_combo.clear()

        if not events:
            self.event_combo.addItem("No events found", None)
            self.status_label.setText("No events found in catalog.")
            self.status_label.setStyleSheet("color: #f0a030; font-size: 10px;")
        else:
            for event in events:
                self.event_combo.addItem(event["title"], event["href"])
            self.status_label.setText(
                f"Found {len(events)} event(s). Select an event and click Search."
            )
            self.status_label.setStyleSheet("color: #4ccd6a; font-size: 10px;")

        self.refresh_btn.setEnabled(True)
        self.search_btn.setEnabled(True)
        self._catalog_worker = None

    def _on_events_error(self, error_msg):
        """Handle catalog fetch error.

        Args:
            error_msg: Error message string.
        """
        self.status_label.setText(error_msg)
        self.status_label.setStyleSheet("color: #ff6b6b; font-size: 10px;")
        self.refresh_btn.setEnabled(True)
        self.search_btn.setEnabled(True)
        self._catalog_worker = None

    def _toggle_bbox_tool(self, checked):
        """Toggle the bbox drawing tool on/off.

        Args:
            checked: Whether the button is now checked.
        """
        if checked:
            self._previous_map_tool = self.canvas.mapTool()
            if self._bbox_tool is None:
                self._bbox_tool = BBoxMapTool(self.canvas)
                self._bbox_tool.bbox_drawn.connect(self._on_bbox_drawn)
            self.canvas.setMapTool(self._bbox_tool)
            self.status_label.setText("Draw a rectangle on the map...")
            self.status_label.setStyleSheet("color: #5cabff; font-size: 10px;")
        else:
            if self._previous_map_tool:
                self.canvas.setMapTool(self._previous_map_tool)
            else:
                self.canvas.unsetMapTool(self._bbox_tool)

    def _on_bbox_drawn(self, rect):
        """Handle a drawn bounding box.

        Args:
            rect: QgsRectangle in EPSG:4326.
        """
        self._drawn_bbox = (
            rect.xMinimum(),
            rect.yMinimum(),
            rect.xMaximum(),
            rect.yMaximum(),
        )
        self.bbox_label.setText(
            f"BBox: {self._drawn_bbox[0]:.4f}, {self._drawn_bbox[1]:.4f}, "
            f"{self._drawn_bbox[2]:.4f}, {self._drawn_bbox[3]:.4f}"
        )
        self.clear_bbox_btn.setEnabled(True)
        self.draw_bbox_btn.setChecked(False)
        self.use_extent_check.setChecked(False)

        if self._previous_map_tool:
            self.canvas.setMapTool(self._previous_map_tool)

        self.status_label.setText("Bounding box set. Click Search to filter.")
        self.status_label.setStyleSheet("color: #4ccd6a; font-size: 10px;")

    def _clear_bbox(self):
        """Clear the drawn bounding box."""
        self._drawn_bbox = None
        self.bbox_label.setText("")
        self.clear_bbox_btn.setEnabled(False)

    def _get_search_bbox(self):
        """Get the bounding box to use for filtering.

        Returns:
            Tuple of (west, south, east, north) in EPSG:4326, or None.
        """
        if self._drawn_bbox:
            return self._drawn_bbox

        if self.use_extent_check.isChecked():
            extent = self.canvas.extent()
            canvas_crs = self.canvas.mapSettings().destinationCrs()
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
            if canvas_crs != wgs84:
                transform = QgsCoordinateTransform(
                    canvas_crs, wgs84, QgsProject.instance()
                )
                extent = transform.transformBoundingBox(extent)
            return (
                extent.xMinimum(),
                extent.yMinimum(),
                extent.xMaximum(),
                extent.yMaximum(),
            )

        return None

    def _search(self):
        """Search for items in the selected event collection."""
        collection_url = self.event_combo.currentData()
        if not collection_url:
            self.status_label.setText("Please select an event first.")
            self.status_label.setStyleSheet("color: #f0a030; font-size: 10px;")
            return

        self.status_label.setText("Fetching items...")
        self.status_label.setStyleSheet("color: #5cabff; font-size: 10px;")
        self.search_btn.setEnabled(False)

        self._items_worker = ItemsFetchWorker(collection_url)
        self._items_worker.finished.connect(self._on_items_fetched)
        self._items_worker.error.connect(self._on_items_error)
        self._items_worker.start()

    def _on_items_fetched(self, items):
        """Handle fetched items.

        Args:
            items: List of STAC item dicts.
        """
        # Apply bbox filter
        bbox = self._get_search_bbox()
        if bbox:
            items = stac_client.filter_items_by_bbox(items, bbox)

        # Apply phase filter
        phase_text = self.phase_combo.currentText().lower()
        if phase_text != "all":
            items = stac_client.filter_items_by_phase(items, phase_text)

        self._items = items
        self._populate_table(items)
        self._add_footprints_to_map(items)

        self.results_label.setText(f"{len(items)} item(s) found")
        self.status_label.setText(
            f"Found {len(items)} item(s). Check items to visualize or download."
        )
        self.status_label.setStyleSheet("color: #4ccd6a; font-size: 10px;")
        self.search_btn.setEnabled(True)
        self._items_worker = None

    def _on_items_error(self, error_msg):
        """Handle item fetch error.

        Args:
            error_msg: Error message string.
        """
        self.status_label.setText(error_msg)
        self.status_label.setStyleSheet("color: #ff6b6b; font-size: 10px;")
        self.search_btn.setEnabled(True)
        self._items_worker = None

    def _populate_table(self, items):
        """Populate the results table with item data.

        Args:
            items: List of STAC item dicts.
        """
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(0)
        self.results_table.setRowCount(len(items))

        for row, item in enumerate(items):
            props = stac_client.get_item_properties(item)

            # Checkbox column
            check_item = QTableWidgetItem()
            check_item.setCheckState(Qt.Unchecked)
            check_item.setFlags(check_item.flags() | Qt.ItemIsUserCheckable)
            self.results_table.setItem(row, 0, check_item)

            # ID
            id_item = QTableWidgetItem(props["id"])
            id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
            self.results_table.setItem(row, 1, id_item)

            # Date
            date_str = props["datetime"]
            if date_str:
                date_str = date_str[:10]
            date_item = QTableWidgetItem(date_str)
            date_item.setFlags(date_item.flags() & ~Qt.ItemIsEditable)
            self.results_table.setItem(row, 2, date_item)

            # Phase
            phase_item = QTableWidgetItem(props["phase"])
            phase_item.setFlags(phase_item.flags() & ~Qt.ItemIsEditable)
            self.results_table.setItem(row, 3, phase_item)

            # Sensor
            sensor_item = QTableWidgetItem(props["sensor"])
            sensor_item.setFlags(sensor_item.flags() & ~Qt.ItemIsEditable)
            self.results_table.setItem(row, 4, sensor_item)

            # Cloud cover
            cloud = props["cloud_cover"]
            cloud_item = QTableWidgetItem()
            cloud_item.setData(
                Qt.DisplayRole,
                float(cloud) if isinstance(cloud, (int, float)) else str(cloud),
            )
            cloud_item.setFlags(cloud_item.flags() & ~Qt.ItemIsEditable)
            self.results_table.setItem(row, 5, cloud_item)

            # GSD
            gsd = props["pan_gsd"]
            gsd_str = f"{gsd:.2f}" if isinstance(gsd, (int, float)) else str(gsd)
            gsd_item = QTableWidgetItem()
            gsd_item.setData(
                Qt.DisplayRole, float(gsd) if isinstance(gsd, (int, float)) else gsd_str
            )
            gsd_item.setFlags(gsd_item.flags() & ~Qt.ItemIsEditable)
            self.results_table.setItem(row, 6, gsd_item)

        self.results_table.setSortingEnabled(True)

    def _add_footprints_to_map(self, items):
        """Add item footprints as a vector layer to the map.

        Args:
            items: List of STAC item dicts.
        """
        # Remove existing footprint layer
        self._remove_footprint_layer()

        if not items:
            return

        # Create memory layer
        layer = QgsVectorLayer(
            "Polygon?crs=epsg:4326"
            "&field=item_id:string"
            "&field=phase:string"
            "&field=date:string"
            "&field=sensor:string",
            "Vantor Footprints",
            "memory",
        )

        provider = layer.dataProvider()
        features = []

        for item in items:
            geom_dict = item.get("geometry")
            if not geom_dict:
                continue

            geom = QgsGeometry.fromPolygonXY(
                [
                    [QgsPointXY(coord[0], coord[1]) for coord in ring]
                    for ring in geom_dict.get("coordinates", [])
                ]
            )

            props = stac_client.get_item_properties(item)
            feat = QgsFeature()
            feat.setGeometry(geom)
            feat.setAttributes(
                [
                    props["id"],
                    props["phase"],
                    props["datetime"][:10] if props["datetime"] else "",
                    props["sensor"],
                ]
            )
            features.append(feat)

        if features:
            provider.addFeatures(features)
            layer.updateExtents()

            # Style the layer with different colors per phase
            from qgis.core import (
                QgsFillSymbol,
                QgsCategorizedSymbolRenderer,
                QgsRendererCategory,
            )

            pre_symbol = QgsFillSymbol.createSimple(
                {
                    "color": "51,136,255,0",
                    "outline_color": "51,136,255,255",
                    "outline_width": "1.0",
                }
            )
            post_symbol = QgsFillSymbol.createSimple(
                {
                    "color": "255,0,0,0",
                    "outline_color": "255,0,0,255",
                    "outline_width": "1.0",
                }
            )
            default_symbol = QgsFillSymbol.createSimple(
                {
                    "color": "128,128,128,0",
                    "outline_color": "128,128,128,200",
                    "outline_width": "0.8",
                }
            )

            categories = [
                QgsRendererCategory("pre", pre_symbol, "Pre-event"),
                QgsRendererCategory("post", post_symbol, "Post-event"),
                QgsRendererCategory("", default_symbol, "Unknown"),
            ]
            renderer = QgsCategorizedSymbolRenderer("phase", categories)
            layer.setRenderer(renderer)

            QgsProject.instance().addMapLayer(layer)
            self._footprint_layer = layer

            # Connect selection changes for map → table sync
            layer.selectionChanged.connect(self._on_map_selection_changed)

            # Zoom to footprints (transform extent to canvas CRS)
            extent = layer.extent()
            canvas_crs = self.canvas.mapSettings().destinationCrs()
            layer_crs = layer.crs()
            if canvas_crs.isValid() and layer_crs.isValid() and canvas_crs != layer_crs:
                transform = QgsCoordinateTransform(
                    layer_crs, canvas_crs, QgsProject.instance()
                )
                extent = transform.transformBoundingBox(extent)
            self.canvas.setExtent(extent)
            self.canvas.refresh()

    def _remove_footprint_layer(self):
        """Remove the existing footprint layer from the map."""
        if self._footprint_layer is None:
            return

        import sip

        if sip.isdeleted(self._footprint_layer):
            self._footprint_layer = None
            return

        try:
            self._footprint_layer.selectionChanged.disconnect(
                self._on_map_selection_changed
            )
        except (RuntimeError, TypeError):
            pass
        try:
            QgsProject.instance().removeMapLayer(self._footprint_layer.id())
        except RuntimeError:
            pass
        self._footprint_layer = None

    def _on_table_selection_changed(self, row, col, prev_row, prev_col):
        """Handle table row selection to highlight footprint on map.

        Args:
            row: Current row index.
            col: Current column index.
            prev_row: Previous row index.
            prev_col: Previous column index.
        """
        if self._updating_selection:
            return

        if row < 0:
            self._highlighter.clear()
            return

        id_cell = self.results_table.item(row, 1)
        if not id_cell:
            return

        self._updating_selection = True

        item_id = id_cell.text()

        # Highlight on map using rubber band only (no layer selection)
        if self._footprint_layer:
            for feat in self._footprint_layer.getFeatures():
                if feat["item_id"] == item_id:
                    # Zoom to feature (transform to canvas CRS)
                    extent = feat.geometry().boundingBox()
                    canvas_crs = self.canvas.mapSettings().destinationCrs()
                    layer_crs = self._footprint_layer.crs()
                    if (
                        canvas_crs.isValid()
                        and layer_crs.isValid()
                        and canvas_crs != layer_crs
                    ):
                        transform = QgsCoordinateTransform(
                            layer_crs, canvas_crs, QgsProject.instance()
                        )
                        extent = transform.transformBoundingBox(extent)
                    self.canvas.setExtent(extent)
                    self.canvas.zoomByFactor(1.2)
                    self._highlighter.highlight_geometry(
                        feat.geometry(), self._footprint_layer
                    )
                    self.canvas.refresh()
                    break

        self._updating_selection = False

    def _on_map_selection_changed(self, selected, deselected, clear_and_select):
        """Handle map feature selection to highlight row in table.

        Args:
            selected: List of selected feature IDs.
            deselected: List of deselected feature IDs.
            clear_and_select: Whether this is a clear-and-select operation.
        """
        if self._updating_selection or not selected:
            return

        self._updating_selection = True

        # Get the item_id of the first selected feature
        if self._footprint_layer:
            for feat in self._footprint_layer.getFeatures():
                if feat.id() in selected:
                    item_id = feat["item_id"]

                    # Find and select the corresponding table row
                    for row in range(self.results_table.rowCount()):
                        id_item = self.results_table.item(row, 1)
                        if id_item and id_item.text() == item_id:
                            self.results_table.selectRow(row)
                            self.results_table.scrollToItem(
                                self.results_table.item(row, 1)
                            )

                            # Highlight with rubber band
                            self._highlighter.highlight_geometry(
                                feat.geometry(), self._footprint_layer
                            )
                            break
                    break

            # Clear the opaque QGIS selection, keep only rubber band
            self._footprint_layer.removeSelection()

        self._updating_selection = False

    def _get_checked_items(self):
        """Get the list of checked items from the table.

        Returns:
            List of (row_index, item_dict) tuples for checked rows.
        """
        # Build lookup by item ID for sorting-safe access
        items_by_id = {item.get("id", ""): item for item in self._items}
        checked = []
        for row in range(self.results_table.rowCount()):
            check_item = self.results_table.item(row, 0)
            if check_item and check_item.checkState() == Qt.Checked:
                id_cell = self.results_table.item(row, 1)
                if id_cell and id_cell.text() in items_by_id:
                    checked.append((row, items_by_id[id_cell.text()]))
        return checked

    def _select_all(self):
        """Check all items in the table."""
        for row in range(self.results_table.rowCount()):
            check_item = self.results_table.item(row, 0)
            if check_item:
                check_item.setCheckState(Qt.Checked)

    def _deselect_all(self):
        """Uncheck all items in the table."""
        for row in range(self.results_table.rowCount()):
            check_item = self.results_table.item(row, 0)
            if check_item:
                check_item.setCheckState(Qt.Unchecked)

    def _visualize_selected(self):
        """Add checked items as COG raster layers."""
        checked = self._get_checked_items()
        if not checked:
            self.status_label.setText("No items selected. Check items first.")
            self.status_label.setStyleSheet("color: #f0a030; font-size: 10px;")
            return

        added = 0
        for _, item in checked:
            cog_url = stac_client.get_cog_url(item)
            if not cog_url:
                continue

            item_id = item.get("id", "Unknown")
            vsicurl_url = f"/vsicurl/{cog_url}"

            layer = QgsRasterLayer(vsicurl_url, item_id)
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)
                added += 1
            else:
                self.iface.messageBar().pushWarning(
                    "Vantor", f"Failed to load raster: {item_id}"
                )

        # Clear the yellow highlight rubber band
        self._highlighter.clear()

        self.status_label.setText(f"Added {added} raster layer(s).")
        self.status_label.setStyleSheet("color: #4ccd6a; font-size: 10px;")

    def _download_selected(self):
        """Download checked COG files to disk."""
        checked = self._get_checked_items()
        if not checked:
            self.status_label.setText("No items selected. Check items first.")
            self.status_label.setStyleSheet("color: #f0a030; font-size: 10px;")
            return

        # Ask for output directory
        output_dir = QFileDialog.getExistingDirectory(
            self, "Select Download Directory", ""
        )
        if not output_dir:
            return

        downloads = []
        for _, item in checked:
            cog_url = stac_client.get_cog_url(item)
            if cog_url:
                downloads.append((item.get("id", "unknown"), cog_url))

        if not downloads:
            self.status_label.setText("No downloadable assets found.")
            self.status_label.setStyleSheet("color: #f0a030; font-size: 10px;")
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.cancel_btn.setVisible(True)
        self.download_btn.setEnabled(False)
        self.visualize_btn.setEnabled(False)

        self._download_worker = DownloadWorker(downloads, output_dir)
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.start()

    def _on_download_progress(self, percent, message):
        """Handle download progress updates.

        Args:
            percent: Progress percentage (0-100).
            message: Status message.
        """
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #5cabff; font-size: 10px;")

    def _cancel_download(self):
        """Cancel the running download."""
        if self._download_worker and self._download_worker.isRunning():
            self._download_worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.status_label.setText("Cancelling download...")
            self.status_label.setStyleSheet("color: #f0a030; font-size: 10px;")

    def _on_download_finished(self, success, message):
        """Handle download completion.

        Args:
            success: Whether the download was successful.
            message: Result message.
        """
        self.progress_bar.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setEnabled(True)
        self.download_btn.setEnabled(True)
        self.visualize_btn.setEnabled(True)

        if success:
            self.status_label.setText(message)
            self.status_label.setStyleSheet("color: #4ccd6a; font-size: 10px;")
            self.iface.messageBar().pushSuccess("Vantor", message)
        else:
            self.status_label.setText(message)
            self.status_label.setStyleSheet("color: #ff6b6b; font-size: 10px;")
            QMessageBox.warning(self, "Download Failed", message)

        self._download_worker = None

    def cleanup(self):
        """Clean up resources when the dock is being removed."""
        self._highlighter.clear()
        self._remove_footprint_layer()

        if self._bbox_tool:
            self._bbox_tool.deactivate()
            self._bbox_tool = None

        # Stop any running workers
        for worker in [self._catalog_worker, self._items_worker, self._download_worker]:
            if worker and worker.isRunning():
                worker.quit()
                worker.wait(3000)

    def closeEvent(self, event):
        """Handle dock widget close event."""
        self._highlighter.clear()
        event.accept()
