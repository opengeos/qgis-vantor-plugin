"""
STAC Catalog Client for Vantor Plugin

Fetches and parses the Vantor Open Data static STAC catalog.
Always fetches fresh from the server (no caching) to ensure
newly added events and items are always visible.
"""

import json
from urllib.request import urlopen, Request
from urllib.parse import urljoin
from typing import Any, Dict, List, Optional, Tuple

CATALOG_URL = "https://vantor-opendata.s3.amazonaws.com/events/catalog.json"


def _fetch_json(url: str) -> Dict[str, Any]:
    """Fetch and parse a JSON file from a URL.

    Args:
        url: The URL to fetch.

    Returns:
        Parsed JSON as a dict.
    """
    req = Request(url, headers={"User-Agent": "QGIS-Vantor-Plugin/0.1"})
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _resolve_href(base_url: str, href: str) -> str:
    """Resolve a relative href against a base URL.

    Args:
        base_url: The base URL (e.g., the parent catalog/collection URL).
        href: The href to resolve (may be relative or absolute).

    Returns:
        The absolute URL.
    """
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return urljoin(base_url, href)


def fetch_catalog() -> List[Dict[str, str]]:
    """Fetch the root catalog and return a list of event collections.

    Always fetches fresh from S3 — no caching.

    Returns:
        List of dicts with keys: id, title, href (absolute URL to collection.json).
    """
    catalog = _fetch_json(CATALOG_URL)
    events = []

    for link in catalog.get("links", []):
        if link.get("rel") == "child":
            href = _resolve_href(CATALOG_URL, link["href"])
            # Extract readable name from URL path when title is missing
            # e.g. ".../events/Typhoon-Gezani-Feb-2026/collection.json"
            # -> "Typhoon-Gezani-Feb-2026"
            fallback_name = href.rstrip("/").split("/")[-2] if "/" in href else href
            title = link.get("title", fallback_name)
            events.append(
                {
                    "id": link.get("title", fallback_name),
                    "title": title,
                    "href": href,
                }
            )

    return events


def fetch_collection(collection_url: str) -> Dict[str, Any]:
    """Fetch a collection and return its metadata.

    Always fetches fresh from S3 — no caching.

    Args:
        collection_url: Absolute URL to the collection.json file.

    Returns:
        Dict with collection metadata including id, title, description,
        and temporal/spatial extent.
    """
    return _fetch_json(collection_url)


def fetch_items(collection_url: str) -> List[Dict[str, Any]]:
    """Fetch all items for a collection.

    Follows item links from the collection JSON and fetches each item.
    Always fetches fresh from S3 — no caching.

    Args:
        collection_url: Absolute URL to the collection.json file.

    Returns:
        List of STAC item dicts.
    """
    collection = _fetch_json(collection_url)
    items = []
    seen_ids = set()

    for link in collection.get("links", []):
        if link.get("rel") == "item":
            item_url = _resolve_href(collection_url, link["href"])
            try:
                item = _fetch_json(item_url)
                item_id = item.get("id", "")
                if item_id not in seen_ids:
                    seen_ids.add(item_id)
                    items.append(item)
            except Exception:
                continue

    return items


def filter_items_by_bbox(
    items: List[Dict[str, Any]], bbox: Tuple[float, float, float, float]
) -> List[Dict[str, Any]]:
    """Filter items whose bounding boxes intersect the given bbox.

    Uses simple rectangle intersection (no shapely dependency needed).

    Args:
        items: List of STAC item dicts.
        bbox: Tuple of (west, south, east, north) in EPSG:4326.

    Returns:
        Filtered list of items that intersect the bbox.
    """
    west, south, east, north = bbox
    filtered = []

    for item in items:
        item_bbox = item.get("bbox")
        if item_bbox and len(item_bbox) >= 4:
            iw, is_, ie, in_ = item_bbox[0], item_bbox[1], item_bbox[2], item_bbox[3]
            # Check rectangle intersection
            if iw <= east and ie >= west and is_ <= north and in_ >= south:
                filtered.append(item)
        else:
            # No bbox available, include the item
            filtered.append(item)

    return filtered


def filter_items_by_phase(
    items: List[Dict[str, Any]], phase: str
) -> List[Dict[str, Any]]:
    """Filter items by pre/post-event phase.

    Args:
        items: List of STAC item dicts.
        phase: One of "pre-event", "post-event", or "all".

    Returns:
        Filtered list of items matching the phase.
    """
    if phase == "all":
        return items

    # Normalize: "pre-event" matches "pre" or "pre-event"
    phase_key = phase.lower().replace("-event", "")
    return [
        item
        for item in items
        if item.get("properties", {}).get("phase", "").lower().replace("-event", "")
        == phase_key
    ]


def get_cog_url(item: Dict[str, Any]) -> Optional[str]:
    """Extract the COG (visual) asset URL from a STAC item.

    Args:
        item: A STAC item dict.

    Returns:
        The COG URL string, or None if not found.
    """
    assets = item.get("assets", {})
    visual = assets.get("visual")
    if visual:
        return visual.get("href")
    # Fallback: look for any geotiff asset
    for asset in assets.values():
        asset_type = asset.get("type", "")
        if "geotiff" in asset_type or "tiff" in asset_type:
            return asset.get("href")
    return None


def get_thumbnail_url(item: Dict[str, Any]) -> Optional[str]:
    """Extract the thumbnail asset URL from a STAC item.

    Args:
        item: A STAC item dict.

    Returns:
        The thumbnail URL string, or None if not found.
    """
    assets = item.get("assets", {})
    thumbnail = assets.get("thumbnail")
    if thumbnail:
        return thumbnail.get("href")
    return None


def get_item_properties(item: Dict[str, Any]) -> Dict[str, Any]:
    """Extract display-relevant properties from a STAC item.

    Args:
        item: A STAC item dict.

    Returns:
        Dict with standardized property keys for display.
    """
    props = item.get("properties", {})
    return {
        "id": item.get("id", "Unknown"),
        "datetime": props.get("datetime", ""),
        "phase": props.get("phase", ""),
        "sensor": props.get("vehicle_name", props.get("constellation", "")),
        "cloud_cover": props.get("eo:cloud_cover", props.get("cloud_cover", "")),
        "pan_gsd": props.get("pan_gsd", props.get("panchromatic_gsd", "")),
        "ms_gsd": props.get("multispectral_gsd", ""),
        "off_nadir": props.get("view:off_nadir", ""),
    }
