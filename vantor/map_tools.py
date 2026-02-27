"""
Map Tools for Vantor Plugin

Custom QgsMapTool implementations for drawing bounding boxes
and selecting footprints on the map canvas.
"""

from qgis.PyQt.QtCore import pyqtSignal, Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsGeometry,
    QgsRectangle,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
)
from qgis.gui import QgsMapTool, QgsRubberBand


class BBoxMapTool(QgsMapTool):
    """Map tool for drawing a bounding box rectangle on the canvas."""

    bbox_drawn = pyqtSignal(QgsRectangle)

    def __init__(self, canvas):
        """Initialize the bbox drawing tool.

        Args:
            canvas: The QGIS map canvas.
        """
        super().__init__(canvas)
        self.canvas = canvas
        self.rubber_band = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
        self.rubber_band.setColor(QColor(255, 0, 0, 100))
        self.rubber_band.setStrokeColor(QColor(255, 0, 0, 200))
        self.rubber_band.setWidth(2)
        self.start_point = None
        self.is_drawing = False

    def canvasPressEvent(self, event):
        """Handle mouse press to start drawing the bbox.

        Args:
            event: The mouse press event.
        """
        if event.button() == Qt.LeftButton:
            self.start_point = self.toMapCoordinates(event.pos())
            self.is_drawing = True
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)

    def canvasMoveEvent(self, event):
        """Handle mouse move to update the bbox visualization.

        Args:
            event: The mouse move event.
        """
        if not self.is_drawing or self.start_point is None:
            return

        current = self.toMapCoordinates(event.pos())
        rect = QgsRectangle(self.start_point, current)
        self.rubber_band.setToGeometry(QgsGeometry.fromRect(rect), None)

    def canvasReleaseEvent(self, event):
        """Handle mouse release to finalize the bbox.

        Args:
            event: The mouse release event.
        """
        if not self.is_drawing or self.start_point is None:
            return

        if event.button() == Qt.LeftButton:
            end_point = self.toMapCoordinates(event.pos())
            rect = QgsRectangle(self.start_point, end_point)

            # Transform to EPSG:4326 if the canvas CRS is different
            canvas_crs = self.canvas.mapSettings().destinationCrs()
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
            if canvas_crs != wgs84:
                transform = QgsCoordinateTransform(
                    canvas_crs, wgs84, QgsProject.instance()
                )
                rect = transform.transformBoundingBox(rect)

            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
            self.is_drawing = False
            self.start_point = None

            if rect.width() > 0 and rect.height() > 0:
                self.bbox_drawn.emit(rect)

    def deactivate(self):
        """Clean up when the tool is deactivated."""
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        self.is_drawing = False
        self.start_point = None
        super().deactivate()


class FootprintHighlighter:
    """Manages highlighting of selected footprints on the map."""

    def __init__(self, canvas):
        """Initialize the highlighter.

        Args:
            canvas: The QGIS map canvas.
        """
        self.canvas = canvas
        self.rubber_bands = []

    def highlight_geometry(self, geometry, layer=None):
        """Highlight a single geometry on the map.

        Args:
            geometry: QgsGeometry to highlight.
            layer: QgsVectorLayer for CRS transform (pass the source layer).
        """
        self.clear()
        rb = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        rb.setColor(QColor(255, 255, 0, 128))
        rb.setStrokeColor(QColor(255, 255, 0, 255))
        rb.setWidth(3)
        rb.setToGeometry(geometry, layer)
        self.rubber_bands.append(rb)
        self.canvas.refresh()

    def highlight_geometries(self, geometries, layer=None):
        """Highlight multiple geometries on the map.

        Args:
            geometries: List of QgsGeometry objects to highlight.
            layer: QgsVectorLayer for CRS transform (pass the source layer).
        """
        self.clear()
        for geom in geometries:
            rb = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
            rb.setColor(QColor(255, 255, 0, 128))
            rb.setStrokeColor(QColor(255, 255, 0, 255))
            rb.setWidth(3)
            rb.setToGeometry(geom, layer)
            self.rubber_bands.append(rb)
        self.canvas.refresh()

    def clear(self):
        """Remove all current highlights."""
        for rb in self.rubber_bands:
            rb.reset(QgsWkbTypes.PolygonGeometry)
            self.canvas.scene().removeItem(rb)
        self.rubber_bands.clear()
