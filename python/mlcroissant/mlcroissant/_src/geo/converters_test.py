"""Tests for STAC to GeoCroissant converter module.

This module contains tests for the converter functionality that transforms
STAC (SpatioTemporal Asset Catalog) metadata into GeoCroissant format.

Test Categories:
    - Utility Functions: Tests for helper functions like name sanitization and version normalization
    - Basic Conversion: Tests for core STAC to GeoCroissant conversion
    - Extended Features: Tests for additional features like checksums and references
    - Error Handling: Tests for proper error handling in various scenarios
"""

import json
from pathlib import Path
from typing import Dict, Any

import pytest

from mlcroissant._src.geo.converters import (
    stac_to_geocroissant,
    sanitize_name,
    ensure_semver,
    _check_geo_dependencies,
    GEOSPATIAL_DEPENDENCIES_AVAILABLE,
)

# Fixtures

@pytest.fixture
def sample_stac_dict() -> Dict[str, Any]:
    """Create a sample STAC dictionary for testing.
    
    This fixture provides a complete STAC Collection object with all common fields
    populated, including spatial/temporal extent, assets, links, and metadata.
    
    Returns:
        Dict containing a valid STAC Collection
    """
    return {
        # Basic metadata
        "type": "Collection",
        "stac_version": "1.0.0",
        "id": "test-collection",
        "title": "Test Collection!",
        "description": "A test STAC collection for GeoCroissant conversion",
        "license": "CC-BY-4.0",
        
        # Extent information
        "extent": {
            "spatial": {
                "bbox": [[-180, -90, 180, 90]]
            },
            "temporal": {
                "interval": [["2023-01-01T00:00:00Z", "2023-12-31T23:59:59Z"]]
            }
        },
        
        # Links to related resources
        "links": [
            {
                "rel": "self",
                "href": "https://example.com/stac.json",
                "type": "application/json"
            },
            {
                "rel": "root",
                "href": "https://example.com/catalog.json",
                "type": "application/json"
            }
        ],
        
        # Data assets
        "assets": {
            "data": {
                "href": "https://example.com/data.tif",
                "type": "image/tiff",
                "title": "Example Data",
                "description": "Sample GeoTIFF data"
            },
            "metadata": {
                "href": "https://example.com/metadata.json",
                "type": "application/json",
                "title": "Metadata",
                "checksum:multihash": "abc123"
            }
        },
        
        # Attribution
        "providers": [
            {
                "name": "Test Organization",
                "url": "https://example.com",
                "roles": ["producer", "host"]
            }
        ],
        "sci:citation": "Test Dataset Citation"
    }

@pytest.fixture
def temp_stac_file(tmp_path, sample_stac_dict):
    """Create a temporary STAC file for testing.
    
    Args:
        tmp_path: pytest fixture providing temporary directory
        sample_stac_dict: fixture providing STAC dictionary
    
    Returns:
        Path to temporary STAC JSON file
    """
    stac_file = tmp_path / "test_stac.json"
    with open(stac_file, 'w') as f:
        json.dump(sample_stac_dict, f, indent=2)
    return stac_file

# Utility Function Tests

def test_stac_name_conversion(sample_stac_dict):
    """Test STAC title/id to GeoCroissant name conversion.
    
    Tests name sanitization in the context of real STAC data:
        - Collection title conversion
        - Special character handling
        - Whitespace normalization
        - ID fallback when title is missing
    """
    if not GEOSPATIAL_DEPENDENCIES_AVAILABLE:
        pytest.skip("Geospatial dependencies not installed")

    # Test with title
    result = stac_to_geocroissant(sample_stac_dict)
    assert result["name"] == "Test-Collection"
    
    # Test without title (falls back to id)
    del sample_stac_dict["title"]
    result = stac_to_geocroissant(sample_stac_dict)
    assert result["name"] == "test-collection"
    
    # Test with special characters
    sample_stac_dict["title"] = "Complex Name! @#$%"
    result = stac_to_geocroissant(sample_stac_dict)
    assert result["name"] == "Complex-Name"

def test_ensure_semver():
    """Test semantic version normalization.
    
    Tests version string normalization to semver format:
        - Two-part versions (append .0)
        - Leading 'v' prefix removal
        - Extra version components (truncate)
        - Empty/None values (default to 1.0.0)
    """
    test_cases = [
        ("1.0", "1.0.0"),       # Two-part version
        ("v1.0.0", "1.0.0"),    # Remove v prefix
        (None, "1.0.0"),        # None value
        ("2.1.3", "2.1.3"),     # Already valid
        ("v2.1", "2.1.0"),      # v prefix and two-part
        ("1.0.0.0", "1.0.0"),   # Extra components
    ]
    
    for input_version, expected in test_cases:
        assert ensure_semver(input_version) == expected

def test_check_geo_dependencies():
    """Test geospatial dependency checking.
    
    Tests proper handling of missing/present geospatial dependencies:
        - When dependencies are missing: raises ImportError
        - When dependencies are present: no error
    """
    if not GEOSPATIAL_DEPENDENCIES_AVAILABLE:
        with pytest.raises(ImportError) as exc_info:
            _check_geo_dependencies()
        assert "Install with: pip install mlcroissant[geo]" in str(exc_info.value)
    else:
        _check_geo_dependencies()  # Should not raise

# Basic STAC Conversion Tests

def test_stac_to_geocroissant_dict(sample_stac_dict):
    """Test basic STAC dictionary conversion.
    
    Verifies the core conversion functionality including:
        - Basic metadata (type, name, version, license)
        - JSON-LD context
        - Spatial/temporal extent
        - Asset distribution
        - Provider information
        - Citations
    """
    if not GEOSPATIAL_DEPENDENCIES_AVAILABLE:
        pytest.skip("Geospatial dependencies not installed")
        
    result = stac_to_geocroissant(sample_stac_dict)
    
    # Check basic metadata
    assert result["@type"] == "Dataset"
    assert result["name"] == "Test-Collection"
    assert result["version"] == "1.0.0"
    assert result["license"] == "CC-BY-4.0"
    assert result["description"] == "A test STAC collection for GeoCroissant conversion"
    
    # Check context
    assert "@context" in result
    assert result["@context"]["geocr"] == "http://mlcommons.org/geocroissant/"
    
    # Check spatial extent
    assert "geocr:BoundingBox" in result
    assert result["geocr:BoundingBox"] == [-180, -90, 180, 90]
    
    # Check temporal extent
    assert "dct:temporal" in result
    assert result["dct:temporal"]["startDate"] == "2023-01-01T00:00:00Z"
    assert result["dct:temporal"]["endDate"] == "2023-12-31T23:59:59Z"
    
    # Check distribution (assets)
    assert len(result["distribution"]) == 2
    data_asset = next(a for a in result["distribution"] if a["name"] == "data")
    assert data_asset["contentUrl"] == "https://example.com/data.tif"
    assert data_asset["encodingFormat"] == "image/tiff"
    
    # Check provider
    assert "creator" in result
    assert result["creator"]["name"] == "Test Organization"
    assert result["creator"]["url"] == "https://example.com"
    
    # Check citation
    assert result["citeAs"] == "Test Dataset Citation"
    assert result["citation"] == "Test Dataset Citation"

def test_stac_to_geocroissant_file(temp_stac_file, tmp_path):
    """Test STAC file I/O operations.
    
    Verifies:
        - Reading from STAC JSON file
        - Writing to GeoCroissant JSON file
        - Content preservation through I/O
        - Basic output validation
    """
    if not GEOSPATIAL_DEPENDENCIES_AVAILABLE:
        pytest.skip("Geospatial dependencies not installed")
        
    output_path = tmp_path / "test_geocroissant.json"
    result = stac_to_geocroissant(temp_stac_file, output_path)
    
    # Check file creation
    assert output_path.exists()
    
    # Load and verify content
    with open(output_path) as f:
        saved = json.load(f)
    assert saved == result
    
    # Check basic validation
    assert "@context" in saved
    assert saved["@type"] == "Dataset"
    assert "name" in saved
    assert "conformsTo" in saved

def test_stac_to_geocroissant_minimal(tmp_path):
    """Test conversion with minimal STAC input.
    
    Verifies handling of minimal STAC input with only required fields:
        - Basic identification (type, id, title)
        - Default value handling
        - Required field presence
    """
    if not GEOSPATIAL_DEPENDENCIES_AVAILABLE:
        pytest.skip("Geospatial dependencies not installed")
        
    minimal_stac = {
        "type": "Collection",
        "id": "minimal",
        "title": "Minimal Test",
        "description": "Minimal STAC collection"
    }
    
    result = stac_to_geocroissant(minimal_stac)
    
    # Check required fields
    assert result["@type"] == "Dataset"
    assert result["name"] == "Minimal-Test"
    assert result["description"] == "Minimal STAC collection"
    assert result["conformsTo"] == "http://mlcommons.org/croissant/1.0"

def test_stac_to_geocroissant_real_data():
    """Test conversion with real STAC data.
    
    Uses a real STAC collection from ICESat-2 Boreal project.
    Test is skipped if the file is not available.
    
    Verifies:
        - Real-world STAC data conversion
        - Complex metadata handling
        - Link and asset conversion
        - Reference mapping
    """
    if not GEOSPATIAL_DEPENDENCIES_AVAILABLE:
        pytest.skip("Geospatial dependencies not installed")
    
    stac_path = Path(__file__).parent / "stac.json"
    if not stac_path.exists():
        pytest.skip("Real STAC data file not found")
    
    result = stac_to_geocroissant(stac_path)
    
    # Basic metadata checks
    assert result["@type"] == "Dataset"
    assert result["name"] == "ICESat-2-Boreal-v2-1-Gridded-Aboveground-Biomass-Density"
    assert result["description"] is not None
    
    # Check references mapping
    assert "references" in result
    refs = {ref["name"]: ref for ref in result["references"]}
    
    # Check GitHub repository reference
    assert "GitHub Repository" in refs
    github_ref = refs["GitHub Repository"]
    assert github_ref["url"] == "https://github.com/lauraduncanson/icesat2_boreal"
    assert github_ref["encodingFormat"] == "text/html"
    
    # Check assets/distribution
    assert "distribution" in result
    dists = {d["name"]: d for d in result["distribution"]}
    
    # Check tiles asset
    assert "tiles" in dists
    tiles = dists["tiles"]
    assert tiles["contentUrl"].startswith("s3://nasa-maap-data-store")
    assert tiles["encodingFormat"] == "application/geopackage+sqlite3"
    
    # Check context
    assert "@context" in result
    assert result["@context"]["geocr"] == "http://mlcommons.org/geocroissant/"
    
    # Check conformance
    assert result["conformsTo"] == "http://mlcommons.org/croissant/1.0"
    
# Error Handling Tests

def test_stac_to_geocroissant_missing_file():
    """Test handling of missing STAC file.
    
    Verifies proper error handling when input file doesn't exist.
    """
    with pytest.raises(FileNotFoundError):
        stac_to_geocroissant("/nonexistent/path.json")

def test_stac_to_geocroissant_invalid_input():
    """Test handling of invalid input types.
    
    Verifies proper error handling for invalid input types:
        - Non-string/Path/dict inputs
        - Type validation
    """
    with pytest.raises(TypeError) as exc_info:
        stac_to_geocroissant(123)  # Invalid input type
    assert "Expected string, Path, or dict input" in str(exc_info.value)