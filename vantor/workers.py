"""
Background Workers for Vantor Plugin

QThread workers for async catalog operations to keep the UI responsive.
"""

import os
from urllib.request import urlopen, Request

from qgis.PyQt.QtCore import QThread, pyqtSignal

from . import stac_client


class CatalogFetchWorker(QThread):
    """Worker thread for fetching the STAC catalog event list.

    Always fetches fresh from S3 — no caching.
    """

    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def run(self):
        """Fetch the root catalog and emit the list of events."""
        try:
            events = stac_client.fetch_catalog()
            self.finished.emit(events)
        except Exception as e:
            self.error.emit(f"Failed to fetch catalog: {str(e)}")


class ItemsFetchWorker(QThread):
    """Worker thread for fetching items from a collection.

    Always fetches fresh from S3 — no caching.
    """

    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, collection_url, parent=None):
        """Initialize the worker.

        Args:
            collection_url: Absolute URL to the collection.json file.
            parent: Parent QObject.
        """
        super().__init__(parent)
        self.collection_url = collection_url

    def run(self):
        """Fetch all items for the collection."""
        try:
            items = stac_client.fetch_items(self.collection_url)
            self.finished.emit(items)
        except Exception as e:
            self.error.emit(f"Failed to fetch items: {str(e)}")


class DownloadWorker(QThread):
    """Worker thread for downloading COG files to disk."""

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, downloads, output_dir, parent=None):
        """Initialize the worker.

        Args:
            downloads: List of (item_id, cog_url) tuples to download.
            output_dir: Directory to save downloaded files.
            parent: Parent QObject.
        """
        super().__init__(parent)
        self.downloads = downloads
        self.output_dir = output_dir
        self._cancelled = False

    def cancel(self):
        """Request cancellation of the download."""
        self._cancelled = True

    def run(self):
        """Download all COG files with byte-level progress."""
        try:
            total = len(self.downloads)
            os.makedirs(self.output_dir, exist_ok=True)
            completed = 0

            for i, (item_id, url) in enumerate(self.downloads):
                if self._cancelled:
                    break

                self.progress.emit(
                    int((i / total) * 100),
                    f"Downloading {item_id} ({i + 1}/{total})...",
                )

                filename = f"{item_id}.tif"
                filepath = os.path.join(self.output_dir, filename)

                req = Request(url, headers={"User-Agent": "QGIS-Vantor-Plugin/0.1"})
                with urlopen(req, timeout=600) as response:  # nosec B310
                    file_size = response.headers.get("Content-Length")
                    file_size = int(file_size) if file_size else None
                    downloaded = 0

                    with open(filepath, "wb") as f:
                        while True:
                            if self._cancelled:
                                break
                            chunk = response.read(65536)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)

                            if file_size:
                                file_pct = downloaded / file_size
                                overall_pct = (i + file_pct) / total * 100
                                size_mb = downloaded / (1024 * 1024)
                                total_mb = file_size / (1024 * 1024)
                                self.progress.emit(
                                    int(overall_pct),
                                    f"Downloading {item_id} ({i + 1}/{total})"
                                    f" - {size_mb:.1f}/{total_mb:.1f} MB",
                                )

                # Remove partial file if cancelled mid-download
                if self._cancelled and os.path.exists(filepath):
                    os.remove(filepath)
                else:
                    completed += 1

            if self._cancelled:
                self.finished.emit(
                    False, f"Download cancelled. {completed} file(s) completed."
                )
            else:
                self.progress.emit(100, f"Downloaded {total} file(s).")
                self.finished.emit(
                    True,
                    f"Successfully downloaded {total} file(s) to {self.output_dir}",
                )

        except Exception as e:
            self.finished.emit(False, f"Download failed: {str(e)}")
