from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    log_loss,
)
from sklearn.model_selection import train_test_split

from app.services.ml_service import (
    DEFAULT_TARGET_COLUMN,
    get_service,
    load_model_artifacts,
    load_training_dataframe,
)


PROJECT_ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
ABLATION_FILE = ARTIFACTS_DIR / "model_ablation_evaluation.json"


DATE_COLUMNS = [
    "date_debut",
    "date_d_acquittement",
    "date_de_reparation",
    "date_de_cloture",
]

TEXT_BUILD_COLUMNS = [
    "ticket_text",
    "origine",
    "etat",
    "type_ticket",
    "priorite",
    "identifiant_n_1",
    "nom_du_site",
    "priorite_texte",
    "mapping_source",
    "site_name",
    "region",
    "incident_match_source",
    "incident_status",
    "worst_priority_code",
    "worst_priority_text",
    "frequency_band",
]


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()

    if isinstance(value, np.ndarray):
        return value.tolist()

    return value


def _add_date_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    parsed_dates: Dict[str, pd.Series] = {}

    for col in DATE_COLUMNS:
        if col in df.columns:
            parsed = pd.to_datetime(
                df[col],
                errors="coerce",
                utc=True,
                dayfirst=True,
            )
        else:
            parsed = pd.Series(pd.NaT, index=df.index)

        parsed_dates[col] = parsed

        df[f"{col}_year"] = parsed.dt.year.fillna(0).astype(int)
        df[f"{col}_month"] = parsed.dt.month.fillna(0).astype(int)
        df[f"{col}_day"] = parsed.dt.day.fillna(0).astype(int)
        df[f"{col}_hour"] = parsed.dt.hour.fillna(0).astype(int)
        df[f"{col}_minute"] = parsed.dt.minute.fillna(0).astype(int)
        df[f"{col}_weekday"] = parsed.dt.weekday.fillna(0).astype(int)

    date_debut = parsed_dates.get("date_debut")
    date_ack = parsed_dates.get("date_d_acquittement")
    date_repair = parsed_dates.get("date_de_reparation")
    date_close = parsed_dates.get("date_de_cloture")

    df["minutes_to_ack"] = (
        ((date_ack - date_debut).dt.total_seconds() / 60.0).fillna(0)
        if date_debut is not None and date_ack is not None
        else 0
    )

    df["minutes_to_repair"] = (
        ((date_repair - date_debut).dt.total_seconds() / 60.0).fillna(0)
        if date_debut is not None and date_repair is not None
        else 0
    )

    df["minutes_to_close"] = (
        ((date_close - date_debut).dt.total_seconds() / 60.0).fillna(0)
        if date_debut is not None and date_close is not None
        else 0
    )

    return df


def _build_combined_text(df: pd.DataFrame, text_column: str) -> pd.DataFrame:
    df = df.copy()
    existing_text_columns = [col for col in TEXT_BUILD_COLUMNS if col in df.columns]

    if not existing_text_columns:
        df[text_column] = ""
        return df

    text_frame = df[existing_text_columns].copy()

    for col in existing_text_columns:
        text_frame[col] = text_frame[col].fillna("").astype(str)

    df[text_column] = text_frame.apply(
        lambda row: " ".join(
            value.strip()
            for value in row.tolist()
            if value and value.strip() and value.strip().lower() != "nan"
        ),
        axis=1,
    )

    return df


def _ensure_feature_columns(
    df: pd.DataFrame,
    feature_columns: List[str],
    numeric_columns: List[str],
    categorical_columns: List[str],
    text_column: str,
) -> pd.DataFrame:
    df = _add_date_features(df)

    if text_column in feature_columns:
        df = _build_combined_text(df, text_column)

    for col in feature_columns:
        if col not in df.columns:
            if col in numeric_columns:
                df[col] = 0
            else:
                df[col] = ""

    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    for col in categorical_columns:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)

    if text_column in df.columns:
        df[text_column] = df[text_column].fillna("").astype(str)

    for col in feature_columns:
        if col in df.columns and col not in numeric_columns:
            df[col] = df[col].fillna("").astype(str)

    return df


def _metrics(y_true, y_pred, y_proba, classes) -> Dict[str, Any]:
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 6),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_true, y_pred)), 6),
        "log_loss": round(float(log_loss(y_true, y_proba, labels=classes)), 6),
        "classification_report": classification_report(
            y_true,
            y_pred,
            labels=classes,
            output_dict=True,
            zero_division=0,
        ),
        "confusion_matrix": {
            "labels": classes,
            "matrix": confusion_matrix(y_true, y_pred, labels=classes).tolist(),
        },
    }


def _neutralize_columns(
    x_test: pd.DataFrame,
    columns_to_neutralize: List[str],
    x_train: pd.DataFrame,
    numeric_columns: List[str],
) -> pd.DataFrame:
    x_modified = x_test.copy()

    for col in columns_to_neutralize:
        if col not in x_modified.columns:
            continue

        if col in numeric_columns:
            train_median = pd.to_numeric(x_train[col], errors="coerce").median()
            value = float(train_median) if not pd.isna(train_median) else 0.0
            x_modified[col] = value
        else:
            x_modified[col] = ""

    return x_modified


def _find_priority_features(feature_columns: List[str]) -> List[str]:
    keywords = [
        "priorite",
        "priority",
        "worst_priority",
    ]

    return [
        col for col in feature_columns
        if any(keyword in col.lower() for keyword in keywords)
    ]


def _find_text_features(feature_columns: List[str], text_column: str) -> List[str]:
    keywords = [
        "ticket_text",
        "combined_text",
        "description",
        "title",
    ]

    features = [
        col for col in feature_columns
        if any(keyword in col.lower() for keyword in keywords)
    ]

    if text_column in feature_columns and text_column not in features:
        features.append(text_column)

    return features


def _find_kpi_engineering_features(feature_columns: List[str]) -> List[str]:
    keywords = [
        "kpi_",
        "incident_potential",
        "matched_incident_count",
        "incident_mapping_confidence",
        "engineering_record_count",
        "actual_load",
        "max_power",
        "pilot_power",
        "azimuth",
        "antheight",
        "mechtilt",
        "electilt",
        "frequency_band",
        "minutes_to_ack",
        "minutes_to_repair",
        "minutes_to_close",
    ]

    return [
        col for col in feature_columns
        if any(keyword in col.lower() for keyword in keywords)
    ]


def evaluate_ablation(
    test_size: float = 0.2,
    random_state: int = 42,
) -> Dict[str, Any]:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    load_model_artifacts()
    service = get_service()

    if service.model is None:
        raise RuntimeError("Model artifacts are not loaded.")

    df = load_training_dataframe()

    target_column = getattr(service, "target_column", DEFAULT_TARGET_COLUMN)

    if target_column not in df.columns:
        raise ValueError(f"Target column '{target_column}' not found in dataframe.")

    feature_columns = list(service.training_feature_columns)
    numeric_columns = list(service.numeric_columns)
    categorical_columns = list(service.categorical_columns)
    text_column = service.text_column

    df = _ensure_feature_columns(
        df=df,
        feature_columns=feature_columns,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        text_column=text_column,
    )

    x = df[feature_columns].copy()
    y = df[target_column].astype(str).copy()

    classifier = service.model.named_steps.get("classifier")
    if classifier is not None and hasattr(classifier, "classes_"):
        classes = [str(item) for item in classifier.classes_.tolist()]
    else:
        classes = sorted(y.unique().tolist())

    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=test_size,
        random_state=random_state,
        stratify=y,
    )

    evaluation_model = clone(service.model)
    evaluation_model.fit(x_train, y_train)

    baseline_pred = evaluation_model.predict(x_test)
    baseline_proba = evaluation_model.predict_proba(x_test)

    priority_features = _find_priority_features(feature_columns)
    text_features = _find_text_features(feature_columns, text_column)
    kpi_engineering_features = _find_kpi_engineering_features(feature_columns)

    ablation_groups = {
        "baseline_all_features": {
            "description": "All features available.",
            "neutralized_features": [],
            "x_eval": x_test,
        },
        "without_priority_features": {
            "description": "Priority-related features are neutralized at test time.",
            "neutralized_features": priority_features,
            "x_eval": _neutralize_columns(
                x_test=x_test,
                columns_to_neutralize=priority_features,
                x_train=x_train,
                numeric_columns=numeric_columns,
            ),
        },
        "without_text_features": {
            "description": "Ticket text / combined text features are neutralized at test time.",
            "neutralized_features": text_features,
            "x_eval": _neutralize_columns(
                x_test=x_test,
                columns_to_neutralize=text_features,
                x_train=x_train,
                numeric_columns=numeric_columns,
            ),
        },
        "without_kpi_engineering_features": {
            "description": "KPI, engineering, and timing context features are neutralized at test time.",
            "neutralized_features": kpi_engineering_features,
            "x_eval": _neutralize_columns(
                x_test=x_test,
                columns_to_neutralize=kpi_engineering_features,
                x_train=x_train,
                numeric_columns=numeric_columns,
            ),
        },
    }

    group_results: Dict[str, Any] = {}

    for group_name, group_payload in ablation_groups.items():
        x_eval = group_payload["x_eval"]

        y_pred = evaluation_model.predict(x_eval)
        y_proba = evaluation_model.predict_proba(x_eval)

        group_results[group_name] = {
            "description": group_payload["description"],
            "neutralized_feature_count": len(group_payload["neutralized_features"]),
            "neutralized_features": group_payload["neutralized_features"],
            "metrics": _metrics(y_test, y_pred, y_proba, classes),
        }

    baseline_accuracy = group_results["baseline_all_features"]["metrics"]["accuracy"]
    baseline_log_loss = group_results["baseline_all_features"]["metrics"]["log_loss"]

    impact_summary = {}

    for group_name, group_result in group_results.items():
        metrics = group_result["metrics"]

        impact_summary[group_name] = {
            "accuracy": metrics["accuracy"],
            "accuracy_drop_vs_baseline": round(
                float(baseline_accuracy - metrics["accuracy"]),
                6,
            ),
            "log_loss": metrics["log_loss"],
            "log_loss_increase_vs_baseline": round(
                float(metrics["log_loss"] - baseline_log_loss),
                6,
            ),
        }

    result = {
        "status": "ok",
        "evaluation_type": "feature_group_neutralization_ablation",
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "rows": int(len(df)),
            "feature_count": int(len(feature_columns)),
            "target_column": target_column,
            "classes": classes,
            "class_distribution": {
                str(label): int(count)
                for label, count in y.value_counts().sort_index().items()
            },
        },
        "split": {
            "test_size": test_size,
            "random_state": random_state,
            "train_rows": int(len(x_train)),
            "test_rows": int(len(x_test)),
        },
        "impact_summary": impact_summary,
        "groups": group_results,
        "interpretation_notes": [
            "This is a feature-group neutralization ablation, not a full retraining ablation.",
            "The model is trained with all features, then selected feature groups are neutralized at test time.",
            "If accuracy drops when a feature group is neutralized, the model depends on that group.",
            "This helps detect whether the RCA model relies too heavily on priority, text, or KPI/engineering features.",
        ],
    }

    with ABLATION_FILE.open("w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2, default=_json_safe)

    return result


def _compact_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": result["status"],
        "evaluated_at_utc": result["evaluated_at_utc"],
        "dataset": result["dataset"],
        "split": result["split"],
        "impact_summary": result["impact_summary"],
        "ablation_file": str(ABLATION_FILE),
        "interpretation_notes": result["interpretation_notes"],
    }


if __name__ == "__main__":
    output = evaluate_ablation()
    print(json.dumps(_compact_summary(output), ensure_ascii=False, indent=2, default=_json_safe))