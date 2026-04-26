"""Shared pytest fixtures.

Stubs the ``qgis`` package so the plugin's modules can be imported without a
running QGIS instance. The stub reproduces the real ``qgis.PyQt`` shim
behavior on Qt6: it re-exports ``QAction``, ``QActionGroup`` and ``QShortcut``
from ``PyQt6.QtGui`` under ``qgis.PyQt.QtWidgets`` (they moved out of
``QtWidgets`` in Qt6).
"""

import sys
import types
from unittest.mock import MagicMock

import PyQt6.QtCore
import PyQt6.QtGui
import PyQt6.QtNetwork
import PyQt6.QtWidgets


class _AnyTypeMeta(type):
    """Metaclass whose attribute access returns the class itself.

    Lets stubbed QGIS classes be used both as types (``class Foo(QgsMapTool)``,
    ``pyqtSignal(QgsRectangle)``) and as enum-like containers (``Qgis.Info``).
    """

    def __getattr__(cls, name: str):
        return cls


class _AnyType(metaclass=_AnyTypeMeta):
    """Type proxy used for any attribute on stubbed ``qgis.core`` / ``qgis.gui``."""


class _ObjectAttrModule(types.ModuleType):
    """Module stub whose attribute access returns ``_AnyType``.

    Used for ``qgis.core`` / ``qgis.gui`` so that constructs evaluated at
    module-import time (subclassing ``QgsMapTool``, declaring
    ``pyqtSignal(QgsRectangle)``, default args like ``level=Qgis.Info``) all
    resolve to a real, attribute-accessible type instead of a ``MagicMock``.
    """

    def __getattr__(self, name: str):
        return _AnyType


def _install_qgis_stub() -> None:
    qgis = types.ModuleType("qgis")
    qgis.__path__ = []
    sys.modules["qgis"] = qgis

    qgis_pyqt = types.ModuleType("qgis.PyQt")
    qgis_pyqt.__path__ = []
    sys.modules["qgis.PyQt"] = qgis_pyqt
    qgis.PyQt = qgis_pyqt

    pyqt_submodules = {
        "QtCore": PyQt6.QtCore,
        "QtGui": PyQt6.QtGui,
        "QtNetwork": PyQt6.QtNetwork,
        "QtWidgets": PyQt6.QtWidgets,
    }
    for name, real in pyqt_submodules.items():
        alias = types.ModuleType(f"qgis.PyQt.{name}")
        for attr in dir(real):
            if not attr.startswith("_"):
                setattr(alias, attr, getattr(real, attr))
        sys.modules[f"qgis.PyQt.{name}"] = alias
        setattr(qgis_pyqt, name, alias)

    # Qt6: QAction, QActionGroup, and QShortcut live in QtGui. The real
    # qgis.PyQt.QtWidgets shim re-exports them, so mirror that here.
    qtwidgets_alias = sys.modules["qgis.PyQt.QtWidgets"]
    for attr in ("QAction", "QActionGroup", "QShortcut"):
        setattr(qtwidgets_alias, attr, getattr(PyQt6.QtGui, attr))

    for submodule in ("QtSvg", "QtWebEngineWidgets"):
        alias = MagicMock()
        sys.modules[f"qgis.PyQt.{submodule}"] = alias
        setattr(qgis_pyqt, submodule, alias)

    for name in ("core", "gui", "utils"):
        stub = _ObjectAttrModule(f"qgis.{name}")
        sys.modules[f"qgis.{name}"] = stub
        setattr(qgis, name, stub)


_install_qgis_stub()
