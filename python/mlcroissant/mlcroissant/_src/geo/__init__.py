"""Geospatial extensions for mlcroissant.

This module provides functionality for working with geospatial datasets,
including converters for STAC catalogs to GeoCroissant format.
"""

from .converters import stac_to_geocroissant

__all__ = ["stac_to_geocroissant"]
