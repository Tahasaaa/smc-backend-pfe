from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple, List

import pandas as pd
import re
import unicodedata


# -------------------------------------------------------------------
# File names
# -------------------------------------------------------------------

SITES_FILE = "master_sites_corrected_synthetic.csv"
ENGINEERING_FILE = "engineering_parameters_corrected_synthetic.csv"
TICKETS_FILE = "tickets_radio_synthetic_linked.csv"


# -------------------------------------------------------------------
# Candidate column names
# Adjust these only if your real CSV headers differ after normalization.
# Normalization rule = lowercase + strip + spaces/hyphens -> underscores
# -------------------------------------------------------------------

SITE_ID_CANDIDATES = ["site_id", "siteid", "site_code", "site_name", "nom_du_site"]

TICKET_ID_CANDIDATES = [
    "ticket_id",
    "ticketid",
    "id",
    "numero_ticket",
    "num_ticket",
]

TICKET_TEXT_CANDIDATES = [
    "ticket_text",
    "description",
    "problem_description",
    "ticket_description",
]

TARGET_CANDIDATES = [
    "rca_family",
    "family",
    "label",
    "target",
    "famille_de_problemes",
    "famille_de_probleme",
]

# -------------------------------------------------------------------
# Small helpers
# -------------------------------------------------------------------

def _project_root() -> Path:
    # app/services/data_pipeline.py -> app/services -> app -> project root
    return Path(__file__).resolve().parents[2]


def _default_data_dir() -> Path:
    return _project_root() / "data"


def _slugify_column_name(col: str) -> str:
    col = str(col).strip().lower()

    # Remove accents: numéro -> numero, problèmes -> problemes
    col = unicodedata.normalize("NFKD", col).encode("ascii", "ignore").decode("ascii")

    # Replace apostrophes and separators with underscores
    col = col.replace("'", "_").replace("’", "_").replace("-", "_").replace(" ", "_")

    # Replace any remaining non-alphanumeric chars with underscore
    col = re.sub(r"[^a-z0-9_]", "_", col)

    # Collapse repeated underscores
    col = re.sub(r"_+", "_", col).strip("_")

    return col


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [_slugify_column_name(col) for col in df.columns]
    return df


def _find_first_existing(df: pd.DataFrame, candidates: List[str], label: str) -> str:
    for col in candidates:
        if col in df.columns:
            return col
    raise ValueError(
        f"Could not find {label}. Tried {candidates}. "
        f"Available columns: {list(df.columns)}"
    )


def _rename_if_found(df: pd.DataFrame, candidates: List[str], canonical_name: str) -> pd.DataFrame:
    df = df.copy()
    for col in candidates:
        if col in df.columns and col != canonical_name:
            df = df.rename(columns={col: canonical_name})
            break
    return df

def _coerce_numeric_columns(df: pd.DataFrame, exclude: Optional[List[str]] = None) -> pd.DataFrame:
    df = df.copy()
    exclude = exclude or []

    for col in df.columns:
        if col in exclude:
            continue

        try:
            df[col] = pd.to_numeric(df[col], errors="raise")
        except (ValueError, TypeError):
            # Leave non-numeric columns unchanged
            pass

    return df


# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------

def load_raw_data(data_dir: Optional[str | Path] = None) -> Dict[str, pd.DataFrame]:
    """
    Load the 3 raw CSV files and normalize their column names.

    Returns:
        {
            "sites": pd.DataFrame,
            "engineering": pd.DataFrame,
            "tickets": pd.DataFrame
        }
    """
    data_path = Path(data_dir) if data_dir else _default_data_dir()

    sites_path = data_path / SITES_FILE
    engineering_path = data_path / ENGINEERING_FILE
    tickets_path = data_path / TICKETS_FILE

    missing = [str(p) for p in [sites_path, engineering_path, tickets_path] if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required CSV files: {missing}")

    sites_df = _normalize_columns(pd.read_csv(sites_path))
    engineering_df = _normalize_columns(pd.read_csv(engineering_path))
    tickets_df = _normalize_columns(pd.read_csv(tickets_path))

    return {
        "sites": sites_df,
        "engineering": engineering_df,
        "tickets": tickets_df,
    }


def validate_raw_data(raw_data: Dict[str, pd.DataFrame]) -> Dict[str, str]:
    """
    Validate minimum required columns and return the detected key columns.
    """
    sites_df = raw_data["sites"]
    engineering_df = raw_data["engineering"]
    tickets_df = raw_data["tickets"]

    sites_site_key = _find_first_existing(sites_df, SITE_ID_CANDIDATES, "site key in sites CSV")
    engineering_site_key = _find_first_existing(engineering_df, SITE_ID_CANDIDATES, "site key in engineering CSV")
    tickets_site_key = _find_first_existing(tickets_df, SITE_ID_CANDIDATES, "site key in tickets CSV")
    tickets_ticket_key = _find_first_existing(tickets_df, TICKET_ID_CANDIDATES, "ticket id in tickets CSV")

    detected = {
        "sites_site_key": sites_site_key,
        "engineering_site_key": engineering_site_key,
        "tickets_site_key": tickets_site_key,
        "tickets_ticket_key": tickets_ticket_key,
    }

    return detected


def build_incident_dataset(raw_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Build the incident-level dataset for V2.

    Goal:
    - 1 row = 1 incident ticket
    - merge ticket data with site data and engineering aggregates by site_id

    Notes:
    - Engineering data is aggregated by site_id.
    - Sites data is deduplicated by site_id.
    - Tickets remain the base table.
    """
    detected = validate_raw_data(raw_data)

    sites_df = raw_data["sites"].copy()
    engineering_df = raw_data["engineering"].copy()
    tickets_df = raw_data["tickets"].copy()

    # Rename detected keys to canonical names
    sites_df = sites_df.rename(columns={detected["sites_site_key"]: "site_id"})
    engineering_df = engineering_df.rename(columns={detected["engineering_site_key"]: "site_id"})
    tickets_df = tickets_df.rename(
        columns={
            detected["tickets_site_key"]: "site_id",
            detected["tickets_ticket_key"]: "ticket_id",
        }
    )

    # Optional canonical rename for text field if present
    tickets_df = _rename_if_found(tickets_df, TICKET_TEXT_CANDIDATES, "ticket_text")

    # Coerce numeric columns where possible
    sites_df = _coerce_numeric_columns(sites_df, exclude=["site_id"])
    engineering_df = _coerce_numeric_columns(engineering_df, exclude=["site_id"])
    tickets_df = _coerce_numeric_columns(tickets_df, exclude=["site_id", "ticket_id", "ticket_text"])

    # Deduplicate sites table to avoid exploding rows on merge
    sites_df = sites_df.drop_duplicates(subset=["site_id"], keep="first")

    # Aggregate engineering data by site_id
    engineering_agg = _aggregate_engineering_by_site(engineering_df)

    # Base = tickets
    incident_df = tickets_df.merge(
        sites_df,
        on="site_id",
        how="left",
        suffixes=("", "_site"),
    )

    incident_df = incident_df.merge(
        engineering_agg,
        on="site_id",
        how="left",
        suffixes=("", "_eng"),
    )

    # Final guard: 1 row = 1 incident ticket
    if "ticket_id" in incident_df.columns:
        incident_df = incident_df.drop_duplicates(subset=["ticket_id"], keep="first")

    return incident_df


def split_features_target(
    incident_df: pd.DataFrame,
    target_column: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Split incident dataset into X and y.

    If target_column is not provided, tries common target candidates.
    """
    df = incident_df.copy()

    if target_column is None:
        target_column = _find_first_existing(df, TARGET_CANDIDATES, "target column")

    if target_column not in df.columns:
        raise ValueError(f"Target column '{target_column}' not found in dataset.")

    y = df[target_column]
    X = df.drop(columns=[target_column])

    return X, y


def summarize_incident_dataset(incident_df: pd.DataFrame) -> Dict[str, object]:
    """
    Useful for quick debugging / smoke tests.
    """
    summary = {
        "rows": int(len(incident_df)),
        "columns": list(incident_df.columns),
        "null_counts": incident_df.isnull().sum().to_dict(),
    }

    if "ticket_id" in incident_df.columns:
        summary["unique_ticket_ids"] = int(incident_df["ticket_id"].nunique())

    if "site_id" in incident_df.columns:
        summary["unique_site_ids"] = int(incident_df["site_id"].nunique())

    return summary


# -------------------------------------------------------------------
# Internal aggregation logic
# -------------------------------------------------------------------

def _aggregate_engineering_by_site(engineering_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate engineering rows at site level.

    Strategy:
    - numeric columns -> mean
    - also keep a count of engineering rows per site
    """
    df = engineering_df.copy()

    if "site_id" not in df.columns:
        raise ValueError("Engineering dataframe must contain 'site_id' before aggregation.")

    numeric_cols = [
        col for col in df.select_dtypes(include=["number"]).columns
        if col != "site_id"
    ]

    if not numeric_cols:
        # If there are no numeric columns, still return a minimal site-level frame
        agg_df = df[["site_id"]].drop_duplicates().copy()
        agg_df["engineering_record_count"] = df.groupby("site_id")["site_id"].transform("count")
        agg_df = agg_df.drop_duplicates(subset=["site_id"])
        return agg_df

    agg_dict = {col: "mean" for col in numeric_cols}
    agg_df = df.groupby("site_id", as_index=False).agg(agg_dict)

    counts = (
        df.groupby("site_id", as_index=False)
        .size()
        .rename(columns={"size": "engineering_record_count"})
    )

    agg_df = agg_df.merge(counts, on="site_id", how="left")
    return agg_df