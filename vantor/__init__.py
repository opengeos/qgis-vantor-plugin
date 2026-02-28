"""
Vantor QGIS Plugin

A QGIS plugin for searching, visualizing, and downloading data
from the Vantor Open Data STAC catalog.
"""

from .deps_manager import ensure_venv_packages_available

# Add venv site-packages to sys.path so plugin dependencies are importable.
# This is a no-op if the venv has not been created yet.
ensure_venv_packages_available()

from .vantor_plugin import VantorPlugin


def classFactory(iface):
    """Load VantorPlugin class.

    Args:
        iface: A QGIS interface instance.

    Returns:
        VantorPlugin: The plugin instance.
    """
    return VantorPlugin(iface)
