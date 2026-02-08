"""Utility functions for the HRH app."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path


# Country name to ISO3 code mapping (can be extended as needed)
COUNTRY_ISO3_MAP = {
    "ethiopia": "ETH",
    "kenya": "KEN",
    "uganda": "UGA",
    "tanzania": "TZA",
    "rwanda": "RWA",
    "burundi": "BDI",
    "somalia": "SOM",
    "south sudan": "SSD",
    "sudan": "SDN",
    "eritrea": "ERI",
    "djibouti": "DJI",
    "malawi": "MWI",
    "zambia": "ZMB",
    "zimbabwe": "ZWE",
    "mozambique": "MOZ",
    "madagascar": "MDG",
    "nigeria": "NGA",
    "ghana": "GHA",
    "senegal": "SEN",
    "mali": "MLI",
    "burkina faso": "BFA",
    "niger": "NER",
    "chad": "TCD",
    "cameroon": "CMR",
    "democratic republic of the congo": "COD",
    "congo": "COG",
    "drc": "COD",
}


def slugify(s: str) -> str:
    """Convert a string to a filesystem-safe slug."""
    s = s.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_-]+', '_', s)
    return s


def detect_country_from_path(path: Path) -> tuple[str | None, str | None]:
    """
    Detect country name and ISO3 code from path segments.

    Scans all path components for known country names or ISO3 codes.

    Args:
        path: File or directory path to scan

    Returns:
        (country_name, iso3) tuple, or (None, None) if not detected
    """
    for part in path.parts:
        part_lower = part.lower()

        # Check if it matches a known country name
        if part_lower in COUNTRY_ISO3_MAP:
            # Return the original case country name and its ISO3 code
            return (part, COUNTRY_ISO3_MAP[part_lower])

        # Check if it's a 3-letter ISO3 code
        if len(part) == 3 and part.isalpha():
            part_upper = part.upper()
            # Check if it's a known ISO3 code
            if part_upper in COUNTRY_ISO3_MAP.values():
                # Find the country name for this ISO3 code
                for name, iso3 in COUNTRY_ISO3_MAP.items():
                    if iso3 == part_upper:
                        return (name.title(), part_upper)

    return (None, None)


def auto_output_name(
    path: str | Path,
    extension: str,
    mode: str | None = None,
    country_name: str | None = None,
    country_iso3: str | None = None
) -> str:
    """
    Generate auto-output filename with country info and timestamp.

    Args:
        path: Path to file or directory (used for country detection and output location)
        extension: Output extension (e.g., 'json', 'md', 'xlsx', 'docx')
        mode: Execution mode ('llm', 'stub', etc.). If None, inferred from path stem
        country_name: Optional country name (auto-detected from path if not provided)
        country_iso3: Optional ISO3 country code (auto-detected from path if not provided)

    Returns:
        Full path to auto-generated output file
    """
    file_path = Path(path)

    # Auto-detect country if not provided
    if not country_name and not country_iso3:
        detected_name, detected_iso3 = detect_country_from_path(file_path)
        country_name = country_name or detected_name
        country_iso3 = country_iso3 or detected_iso3

    # Infer mode from path stem if not provided
    if not mode:
        stem = file_path.stem if file_path.is_file() else ""
        if "output_llm" in stem:
            mode = "llm"
        elif "output_stub" in stem:
            mode = "stub"
        else:
            mode = "out"

    # Get country token
    country_token = ""
    if country_iso3:
        country_token = country_iso3.upper()
    elif country_name:
        country_token = slugify(country_name)

    # Generate timestamp
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # Build filename
    parts = ["output", mode]
    if country_token:
        parts.append(country_token)
    parts.append(stamp)

    filename = "_".join(parts) + f".{extension}"

    # Output to same directory as the path
    # If path has a file extension, use parent directory; otherwise use path itself
    if file_path.suffix:  # Has extension like .json, .xlsx -> it's a file
        output_dir = file_path.parent
    else:  # No extension -> it's a directory
        output_dir = file_path

    return str(output_dir / filename)
