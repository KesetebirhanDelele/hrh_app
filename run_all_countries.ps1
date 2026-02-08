# ============================================================================
# HRH Multi-Country Analysis Runner (Auto-Discovery)
# ============================================================================
# This script automatically discovers and processes all countries in data/sources/
#
# Usage:
#   .\run_all_countries.ps1
#
# Requirements:
#   - Python environment with hrh_app installed
#   - OPENAI_API_KEY set in environment
#   - Source files organized in data/sources/{ISO3}/pdf/ and data/sources/{ISO3}/docx/
#   - The script will auto-generate {iso3}_sources.json from the source files
# ============================================================================

# Enable strict citations mode
$env:HRH_STRICT_CITATIONS = "1"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   HRH Multi-Country Analysis Runner       " -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ISO3 to Country Name mapping
$countryNames = @{
    "ETH" = "Ethiopia"
    "KEN" = "Kenya"
    "UGA" = "Uganda"
    "TZA" = "Tanzania"
    "RWA" = "Rwanda"
    "BDI" = "Burundi"
    "SOM" = "Somalia"
    "SSD" = "South Sudan"
    "ZMB" = "Zambia"
    "MWI" = "Malawi"
    "MOZ" = "Mozambique"
    "ZWE" = "Zimbabwe"
    "BWA" = "Botswana"
    "NAM" = "Namibia"
    "ZAF" = "South Africa"
    "LSO" = "Lesotho"
    "SWZ" = "Eswatini"
    "AGO" = "Angola"
    "COD" = "Democratic Republic of Congo"
    "COG" = "Republic of Congo"
}

# Auto-discover countries by scanning data/sources/ directory
Write-Host "Scanning data/sources/ for country folders..." -ForegroundColor Yellow
$sourcesPath = "data/sources"

if (-not (Test-Path $sourcesPath)) {
    Write-Host "Error: $sourcesPath directory not found!" -ForegroundColor Red
    exit 1
}

$countries = @()
$discoveredFolders = Get-ChildItem -Path $sourcesPath -Directory | Where-Object { $_.Name -match '^[A-Z]{3}$' }

foreach ($folder in $discoveredFolders) {
    $iso3 = $folder.Name
    $countryName = $countryNames[$iso3]

    # If country not in mapping, use ISO3 as name
    if (-not $countryName) {
        $countryName = $iso3
        Write-Host "  Warning: No name mapping for $iso3, using ISO3 code" -ForegroundColor Yellow
    }

    $countries += @{
        Name       = $countryName
        ISO3       = $iso3
        SourceFile = "data/sources/$($iso3.ToLower())_sources.json"
    }

    Write-Host "  Found: $countryName ($iso3)" -ForegroundColor Green
}

if ($countries.Count -eq 0) {
    Write-Host ""
    Write-Host "No country folders found in $sourcesPath!" -ForegroundColor Red
    Write-Host "Expected folder structure: data/sources/ETH/, data/sources/KEN/, etc." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Discovered $($countries.Count) country/countries to process" -ForegroundColor Cyan
Write-Host ""

# Track results
$results = @()
$startTime = Get-Date

foreach ($country in $countries) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Processing: $($country.Name) ($($country.ISO3))" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""

    $countryStartTime = Get-Date
    $success = $true

    try {
        # Step 1: Scan sources (auto-generate sources JSON from PDF/DOCX files)
        Write-Host "[STEP 1/3] Scanning sources..." -ForegroundColor Yellow
        python -m app.app sources-scan --country-iso3 $country.ISO3
        if ($LASTEXITCODE -ne 0) {
            throw "sources-scan failed with exit code $LASTEXITCODE"
        }

        # Step 2: Run all jobs with LLM
        Write-Host "[STEP 2/3] Running all jobs with LLM..." -ForegroundColor Yellow
        python -m app.app run-all --mode llm --country-name $country.Name --country-iso3 $country.ISO3 --sources $country.SourceFile

        if ($LASTEXITCODE -ne 0) {
            throw "run-all failed with exit code $LASTEXITCODE"
        }

        # Step 3: Render outputs (DOCX and XLSX)
        Write-Host "[STEP 3/3] Rendering outputs..." -ForegroundColor Yellow
        python -m app.app render-all --mode llm --country-name $country.Name --country-iso3 $country.ISO3

        if ($LASTEXITCODE -ne 0) {
            throw "render-all failed with exit code $LASTEXITCODE"
        }

        $countryDuration = (Get-Date) - $countryStartTime
        Write-Host ""
        Write-Host "Success: $($country.Name) completed" -ForegroundColor Green
        Write-Host "  Duration: $($countryDuration.ToString('hh\:mm\:ss'))" -ForegroundColor Gray
    }
    catch {
        $success = $false
        $countryDuration = (Get-Date) - $countryStartTime
        Write-Host ""
        Write-Host "Failed: $($country.Name) - $_" -ForegroundColor Red
        Write-Host "  Duration: $($countryDuration.ToString('hh\:mm\:ss'))" -ForegroundColor Gray
    }

    $results += @{
        Country  = $country.Name
        ISO3     = $country.ISO3
        Success  = $success
        Duration = $countryDuration
    }
}

# Print summary
$totalDuration = (Get-Date) - $startTime
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "              SUMMARY                       " -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

foreach ($result in $results) {
    if ($result.Success) {
        Write-Host "SUCCESS: $($result.Country) ($($result.ISO3))" -ForegroundColor Green
    } else {
        Write-Host "FAILED: $($result.Country) ($($result.ISO3))" -ForegroundColor Red
    }
    Write-Host "  Duration: $($result.Duration.ToString('hh\:mm\:ss'))" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Total Duration: $($totalDuration.ToString('hh\:mm\:ss'))" -ForegroundColor Cyan

$successCount = ($results | Where-Object { $_.Success }).Count
$totalCount = $results.Count

if ($successCount -eq $totalCount) {
    Write-Host ""
    Write-Host "All countries processed successfully!" -ForegroundColor Green
    exit 0
} else {
    Write-Host ""
    Write-Host "$successCount/$totalCount countries succeeded" -ForegroundColor Yellow
    exit 1
}
