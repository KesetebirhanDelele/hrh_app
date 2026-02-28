# tools/comparator_index.py
import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

NUMERIC_COLS_DEFAULT = [
    "GDP", "Population", "Urban Pop",
    "MMR", "U5M", "NMR", "CPR", "TFR",
    "PHC"
]


def normalize_colnames(cols):
    out = []
    for c in cols:
        c2 = re.sub(r"\s+", " ", str(c)).strip()
        out.append(c2)
    return out


def zscore(series: pd.Series) -> pd.Series:
    s = series.astype(float)
    mu = s.mean()
    sd = s.std(ddof=0)
    if sd == 0 or np.isnan(sd):
        return pd.Series([0.0] * len(s), index=s.index)
    return (s - mu) / sd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="Path to Excel file")
    ap.add_argument("--sheet", default=None, help="Sheet name (optional)")
    ap.add_argument("--country", required=True, help="Target country name (e.g., Ethiopia)")
    ap.add_argument("--topk", type=int, default=20)
    ap.add_argument("--numeric_cols", default=",".join(NUMERIC_COLS_DEFAULT))
    ap.add_argument("--weights", default=None,
                    help="Optional weights as col=weight,... e.g. MMR=1,U5M=1,NMR=1,TFR=0.7,CPR=0.7,PHC=1")
    ap.add_argument("--peer_filter", action="store_true",
                    help="Apply peer filtering by Income group + Region + CHP + Types of CHW if present (recommended)")
    args = ap.parse_args()

    xls_path = Path(args.file)
    if not xls_path.exists():
        raise SystemExit(f"File not found: {xls_path}")

    sheet_to_read = args.sheet if args.sheet is not None else 0
    df = pd.read_excel(xls_path, sheet_name=sheet_to_read)
    df.columns = normalize_colnames(df.columns)

    if "Country" not in df.columns:
        raise SystemExit("Expected a 'Country' column in the Excel file.")

    numeric_cols = [c.strip() for c in args.numeric_cols.split(",") if c.strip()]
    existing_numeric = [c for c in numeric_cols if c in df.columns]
    if len(existing_numeric) == 0:
        raise SystemExit(
            f"None of the numeric columns were found. Looked for: {numeric_cols}\nAvailable: {list(df.columns)}"
        )

    for c in existing_numeric:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Drop rows missing too much numeric data
    df["_missing_n"] = df[existing_numeric].isna().sum(axis=1)
    df = df[df["_missing_n"] <= max(2, int(len(existing_numeric) * 0.25))].copy()

    # Locate target row (Ethiopia)
    target_mask = df["Country"].astype(str).str.strip().str.lower() == args.country.strip().lower()
    if target_mask.sum() != 1:
        raise SystemExit(f"Could not uniquely find target country '{args.country}'. Matches found: {int(target_mask.sum())}")

    target = df.loc[target_mask].iloc[0]

    # Optional peer filter (only narrows candidate set)
    candidates = df.copy()
    peer_cols = [c for c in ["Income group", "Region", "CHP", "Types of CHW"] if c in df.columns]
    if args.peer_filter and peer_cols:
        for pc in peer_cols:
            tv = target.get(pc, None)
            if pd.notna(tv) and str(tv).strip() != "":
                candidates = candidates[candidates[pc].astype(str).str.strip() == str(tv).strip()].copy()

    # Remove target from candidates
    candidates = candidates[candidates["Country"].astype(str).str.strip().str.lower() != args.country.strip().lower()].copy()

    # Weights
    weights = {c: 1.0 for c in existing_numeric}
    if args.weights:
        for part in args.weights.split(","):
            part = part.strip()
            if not part:
                continue
            k, v = part.split("=")
            k = k.strip()
            v = float(v.strip())
            if k in weights:
                weights[k] = v

    # Z-score normalize across (candidates + target) so distances are comparable
    all_df = pd.concat([candidates, df.loc[target_mask]], axis=0).copy()
    for c in existing_numeric:
        all_df[f"z_{c}"] = zscore(all_df[c])

    target_row = all_df[all_df["Country"].astype(str).str.strip().str.lower() == args.country.strip().lower()].iloc[0]

    # Weighted Euclidean distance in z-space
    def dist(row):
        s = 0.0
        for c in existing_numeric:
            w = weights.get(c, 1.0)
            a = row[f"z_{c}"]
            b = target_row[f"z_{c}"]
            if np.isnan(a) or np.isnan(b):
                continue
            s += w * (a - b) ** 2
        return float(np.sqrt(s))

    scored = all_df[all_df["Country"].astype(str).str.strip().str.lower() != args.country.strip().lower()].copy()
    scored["similarity_distance"] = scored.apply(dist, axis=1)
    scored = scored.sort_values("similarity_distance", ascending=True)

    # Print top-k
    peer_cols_present = [pc for pc in ["Region", "Income group", "CHP", "Types of CHW"] if pc in df.columns]
    out_cols = ["Country"] + peer_cols_present + ["similarity_distance"]

    print("\n=== TARGET ===")
    print(target[["Country"] + peer_cols_present + existing_numeric].to_string())

    print("\n=== SIMILARITY DISTANCE (TOP-K) ===")
    print(scored[out_cols + existing_numeric].head(args.topk).to_string(index=False))

    # Save one file
    out_path = Path("outputs") / "comparator_index"
    out_path.mkdir(parents=True, exist_ok=True)
    scored.to_csv(out_path / "similarity_distance.csv", index=False)
    print(f"\nWrote:\n- {out_path/'similarity_distance.csv'}")


if __name__ == "__main__":
    main()
