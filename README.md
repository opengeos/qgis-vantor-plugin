# qgis-vantor-plugin

[![QGIS Plugin](https://img.shields.io/badge/QGIS-Plugin-green.svg)](https://plugins.qgis.org/plugins/vantor)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A QGIS plugin for searching, visualizing, and downloading data from the [Vantor Open Data](https://radiantearth.github.io/stac-browser/#/external/vantor-opendata.s3.amazonaws.com/events/catalog.json) STAC catalog.

![](https://github.com/user-attachments/assets/360372f7-3287-432e-92ce-4bff1869d1f8)

## Features

- Browse disaster event collections from the Vantor STAC catalog
- Search imagery by map extent or drawn bounding box
- Filter by event and pre/post-event phase
- Visualize Cloud-Optimized GeoTIFF (COG) imagery directly in QGIS
- Download selected imagery to disk
- Interactive footprint display with bidirectional table/map selection
- One-click dependency installer using uv for fast cross-platform package management

## Installation

### From QGIS Plugin Repository

1. Open QGIS Plugin Manager and search for "Vantor"
2. Click **Install** to install the plugin

### From Source

```bash
git clone https://github.com/opengeos/qgis-vantor-plugin.git
cd qgis-vantor-plugin
python install.py
```

Then restart QGIS and enable the **Vantor** plugin in **Plugins > Manage and Install Plugins**.

### First Run

1. Open the **Settings** panel from the Vantor toolbar
2. Go to the **Dependencies** tab
3. Click **Install Dependencies** to install `pystac`
4. Restart QGIS

## Usage

1. Open the **Vantor Panel** from the toolbar
2. Select an event from the dropdown (events are fetched live from the catalog)
3. Optionally filter by phase (Pre-event / Post-event) and spatial extent
4. Click **Search** to fetch items and display footprints on the map
5. Click on a table row to highlight the footprint on the map (and vice versa)
6. Check items and click **Visualize** to stream COG imagery or **Download** to save to disk

![](https://github.com/user-attachments/assets/39c45160-66bd-4ca4-b669-1e06ee74850f)

## Packaging

```bash
python package_plugin.py
```

This creates a `vantor-{version}.zip` file ready for upload to the QGIS plugin repository.

## License

[MIT](LICENSE)
