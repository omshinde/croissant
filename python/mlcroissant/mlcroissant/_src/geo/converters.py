"""Convert geospatial datasets to GeoCroissant format.

This module provides functions to convert various geospatial dataset formats
(STAC, GeoJSON, etc.) to the GeoCroissant JSON-LD format.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    import pystac
    import geopandas as gpd
    import shapely
    import pyproj
    import rasterio
    GEOSPATIAL_DEPENDENCIES_AVAILABLE = True
except ImportError:
    GEOSPATIAL_DEPENDENCIES_AVAILABLE = False

logger = logging.getLogger(__name__)


def _check_geo_dependencies() -> None:
    """Check if geospatial dependencies are installed."""
    if not GEOSPATIAL_DEPENDENCIES_AVAILABLE:
        raise ImportError(
            "Geospatial dependencies not found. "
            "Install with: pip install mlcroissant[geo]"
        )


def sanitize_name(name: str) -> str:
    """Sanitize name for use in Croissant format."""
    return re.sub(r"[^a-zA-Z0-9_\-]", "-", name)


def ensure_semver(version: Optional[str]) -> str:
    """Ensure version follows semver format."""
    if not version:
        return "1.0.0"
    if version.startswith("v"):
        version = version[1:]
    parts = version.split(".")
    if len(parts) == 2:
        parts.append("0")
    return ".".join(parts[:3])


def stac_to_geocroissant(
    stac_input: Union[str, Path, Dict[str, Any]], 
    output_path: Optional[Union[str, Path]] = None
) -> Dict[str, Any]:
    """Convert STAC catalog/collection to GeoCroissant JSON-LD format.
    
    Args:
        stac_input: STAC dictionary OR path to STAC file
        output_path: Optional output file path (if provided, saves to file)
        
    Returns:
        GeoCroissant JSON-LD dictionary
        
    Raises:
        ImportError: If geospatial dependencies are not installed
        ValueError: If STAC data is invalid
        FileNotFoundError: If stac_input file path does not exist
    """
    _check_geo_dependencies()
    
    # Handle file input
    if isinstance(stac_input, (str, Path)):
        stac_path = Path(stac_input)
        if not stac_path.exists():
            raise FileNotFoundError(f"STAC file not found: {stac_path}")
        
        logger.info(f"Loading STAC file: {stac_path}")
        with open(stac_path, 'r') as f:
            stac_dict = json.load(f)
    else:
        stac_dict = stac_input

    dataset_id = stac_dict.get("id")
    name = sanitize_name(stac_dict.get("title", dataset_id or "UnnamedDataset"))
    version = ensure_semver(stac_dict.get("version", "1.0.0"))

    croissant = {
        "@context": {
            "@language": "en",
            "@vocab": "https://schema.org/",
            "cr": "http://mlcommons.org/croissant/",
            "geocr": "http://mlcommons.org/geocroissant/",
            "dct": "http://purl.org/dc/terms/",
            "sc": "https://schema.org/",
            "citeAs": "cr:citeAs",
            "column": "cr:column",
            "conformsTo": "dct:conformsTo",
            "data": {"@id": "cr:data", "@type": "@json"},
            "dataBiases": "cr:dataBiases",
            "dataCollection": "cr:dataCollection",
            "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
            "extract": "cr:extract",
            "field": "cr:field",
            "fileProperty": "cr:fileProperty",
            "fileObject": "cr:fileObject",
            "fileSet": "cr:fileSet",
            "format": "cr:format",
            "includes": "cr:includes",
            "isLiveDataset": "cr:isLiveDataset",
            "jsonPath": "cr:jsonPath",
            "key": "cr:key",
            "md5": {"@id": "cr:md5", "@type": "sc:Text"},
            "sha256": {"@id": "cr:sha256", "@type": "sc:Text"},
            "parentField": "cr:parentField",
            "path": "cr:path",
            "personalSensitiveInformation": "cr:personalSensitiveInformation",
            "recordSet": "cr:recordSet",
            "references": "cr:references",
            "regex": "cr:regex",
            "repeated": "cr:repeated",
            "replace": "cr:replace",
            "separator": "cr:separator",
            "source": "cr:source",
            "subField": "cr:subField",
            "transform": "cr:transform"
        },
        "@type": "Dataset",
        "@id": dataset_id,
        "name": name,
        "description": stac_dict.get("description", ""),
        "version": version,
        "license": stac_dict.get("license", "CC-BY-4.0"),
        "conformsTo": "http://mlcommons.org/croissant/1.0"
    }

    if "sci:citation" in stac_dict:
        croissant["citeAs"] = stac_dict["sci:citation"]
        croissant["citation"] = stac_dict["sci:citation"]

    if stac_dict.get("providers"):
        provider = stac_dict["providers"][0]
        croissant["creator"] = {
            "@type": "Organization",
            "name": provider.get("name", "Unknown"),
            "url": provider.get("url", "")
        }

    # Handle 'self' URL
    for link in stac_dict.get("links", []):
        if link.get("rel") == "self":
            croissant["url"] = link.get("href")
            break

    # Handle other STAC references
    references = []
    for link in stac_dict.get("links", []):
        rel = link.get("rel")
        href = link.get("href")
        if not href or rel == "self":
            continue

        name_map = {
            "root": "STAC root catalog",
            "parent": "STAC parent catalog",
            "items": "STAC item list",
            "about": "GitHub Repository",
            "predecessor-version": "Previous version",
            "http://www.opengis.net/def/rel/ogc/1.0/queryables": "Queryables"
        }

        references.append({
            "@type": "CreativeWork",
            "url": href,
            "name": name_map.get(rel, rel),
            "encodingFormat": link.get("type", "application/json")
        })

    if references:
        croissant["references"] = references

    # Spatial and temporal extent
    spatial = stac_dict.get("extent", {}).get("spatial", {}).get("bbox")
    if spatial:
        croissant["geocr:BoundingBox"] = spatial[0]

    temporal = stac_dict.get("extent", {}).get("temporal", {}).get("interval")
    if temporal and temporal[0]:
        start, end = temporal[0][0], temporal[0][1]
        croissant["dct:temporal"] = {"startDate": start, "endDate": end}
        croissant["datePublished"] = start
    else:
        croissant["datePublished"] = datetime.utcnow().isoformat() + "Z"

    # Asset-level distribution
    croissant["distribution"] = []
    for key, asset in stac_dict.get("assets", {}).items():
        file_object = {
            "@type": "cr:FileObject",
            "@id": key,
            "name": key,
            "description": asset.get("description", asset.get("title", "")),
            "contentUrl": asset.get("href"),
            "encodingFormat": asset.get("type", "application/octet-stream"),
            "sha256": "https://github.com/mlcommons/croissant/issues/80",
            "md5": "https://github.com/mlcommons/croissant/issues/80"
        }

        if "checksum:multihash" in asset:
            file_object["sha256"] = asset["checksum:multihash"]
        elif "file:checksum" in asset:
            file_object["sha256"] = asset["file:checksum"]
        if "checksum:md5" in asset:
            file_object["md5"] = asset["checksum:md5"]

        croissant["distribution"].append(file_object)

    # item_assets as fileSet templates
    if "item_assets" in stac_dict:
        croissant["fileSet"] = []
        for key, asset in stac_dict["item_assets"].items():
            file_obj = {
                "@type": "cr:FileObject",
                "@id": key,
                "name": key,
                "description": asset.get("description", asset.get("title", "")),
                "encodingFormat": asset.get("type", "application/octet-stream"),
                "sha256": "https://github.com/mlcommons/croissant/issues/80",
                "md5": "https://github.com/mlcommons/croissant/issues/80"
            }
            file_set = {
                "@type": "cr:FileSet",
                "name": f"Template for {key}",
                "includes": [file_obj]
            }
            croissant["fileSet"].append(file_set)

    if "renders" in stac_dict:
        croissant["geocr:visualizations"] = stac_dict["renders"]

    if "summaries" in stac_dict:
        croissant["geocr:summaries"] = stac_dict["summaries"]

    if "stac_extensions" in stac_dict:
        croissant["geocr:stac_extensions"] = stac_dict["stac_extensions"]
    if "stac_version" in stac_dict:
        croissant["geocr:stac_version"] = stac_dict["stac_version"]

    if "deprecated" in stac_dict:
        croissant["isLiveDataset"] = not stac_dict["deprecated"]

    # Report unmapped fields
    mapped_keys = {
        "id", "type", "links", "title", "assets", "extent",
        "license", "version", "providers", "description", "sci:citation",
        "renders", "summaries", "stac_extensions", "stac_version", "deprecated", "item_assets"
    }
    extra_fields = {k: v for k, v in stac_dict.items() if k not in mapped_keys}
    logger.info("Unmapped STAC Fields:")
    if extra_fields:
        for k, v in extra_fields.items():
            logger.info(f"- {k}: {type(v).__name__}")
    else:
        logger.info("None")

    # Save to file if output_path provided
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(croissant, f, indent=2)
        logger.info(f"GeoCroissant saved to: {output_path}")

    return croissant
