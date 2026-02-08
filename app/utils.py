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


def create_timestamped_folder(
    base_dir: str | Path,
    country_name: str | None = None,
    country_iso3: str | None = None,
    timestamp: str | None = None
) -> Path:
    """
    Create a timestamped country folder for outputs.

    Args:
        base_dir: Base directory (e.g., outputs/job_id/)
        country_name: Optional country name (auto-detected from path if not provided)
        country_iso3: Optional ISO3 country code (auto-detected from path if not provided)
        timestamp: Optional timestamp string (generated if not provided)

    Returns:
        Path to the created timestamped folder
    """
    base_path = Path(base_dir)

    # Auto-detect country if not provided
    if not country_name and not country_iso3:
        detected_name, detected_iso3 = detect_country_from_path(base_path)
        country_name = country_name or detected_name
        country_iso3 = country_iso3 or detected_iso3

    # Get country token
    country_token = ""
    if country_iso3:
        country_token = country_iso3.upper()
    elif country_name:
        country_token = slugify(country_name).title()

    # Generate timestamp if not provided
    if not timestamp:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # Build folder name
    if country_token:
        folder_name = f"{country_token}_{timestamp}"
    else:
        folder_name = f"run_{timestamp}"

    folder_path = base_path / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)

    return folder_path


def auto_output_name(
    path: str | Path,
    extension: str,
    mode: str | None = None,
    country_name: str | None = None,
    country_iso3: str | None = None
) -> str:
    """
    Generate output filename in a timestamped country folder.

    Args:
        path: Path to file or directory (used for country detection and output location)
        extension: Output extension (e.g., 'json', 'md', 'xlsx', 'docx')
        mode: Execution mode ('llm', 'stub', etc.). If None, inferred from path stem
        country_name: Optional country name (auto-detected from path if not provided)
        country_iso3: Optional ISO3 country code (auto-detected from path if not provided)

    Returns:
        Full path to output file in timestamped folder
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

    # Determine base directory
    if file_path.suffix:  # Has extension -> it's a file
        base_dir = file_path.parent
    else:  # No extension -> it's a directory
        base_dir = file_path

    # Check if we're already in a timestamped folder
    # (folder name matches pattern: COUNTRY_YYYYMMDD_HHMMSS or run_YYYYMMDD_HHMMSS)
    folder_name = base_dir.name
    if "_" in folder_name:
        parts = folder_name.split("_")
        # Check if last two parts look like timestamp: YYYYMMDD_HHMMSS
        if len(parts) >= 2 and len(parts[-1]) == 6 and len(parts[-2]) == 8:
            if parts[-1].isdigit() and parts[-2].isdigit():
                # Already in a timestamped folder, use it directly
                output_dir = base_dir
            else:
                # Not in a timestamped folder, create one
                output_dir = create_timestamped_folder(base_dir, country_name, country_iso3)
        else:
            # Not in a timestamped folder, create one
            output_dir = create_timestamped_folder(base_dir, country_name, country_iso3)
    else:
        # Not in a timestamped folder, create one
        output_dir = create_timestamped_folder(base_dir, country_name, country_iso3)

    # Build simple filename without timestamp (folder has the timestamp)
    filename = f"output_{mode}.{extension}"

    return str(output_dir / filename)
