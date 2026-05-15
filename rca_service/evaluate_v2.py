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
EVALUATION_FILE = ARTIFACTS_DIR / "model_evaluation.json"


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

    # Extra safety: any object-like feature should not contain NaN.
    for col in feature_columns:
        if col in df.columns and col not in numeric_columns:
            df[col] = df[col].fillna("").astype(str)

    return df


def _evaluate_predictions(
    y_true,
    y_pred,
    y_proba,
    classes,
) -> Dict[str, Any]:
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


def _compact_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    test_metrics = result["holdout_test_metrics"]

    return {
        "status": result["status"],
        "evaluated_at_utc": result["evaluated_at_utc"],
        "dataset": result["dataset"],
        "split": result["split"],
        "holdout_test_accuracy": test_metrics["accuracy"],
        "holdout_test_balanced_accuracy": test_metrics["balanced_accuracy"],
        "holdout_test_log_loss": test_metrics["log_loss"],
        "holdout_test_confusion_matrix": test_metrics["confusion_matrix"],
        "holdout_test_classification_report": test_metrics["classification_report"],
        "evaluation_file": str(EVALUATION_FILE),
    }


def evaluate_model(
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

    missing_features = [col for col in feature_columns if col not in df.columns]
    if missing_features:
        raise ValueError(
            "Some training feature columns are still missing after feature engineering: "
            + ", ".join(missing_features[:30])
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

    y_train_pred = evaluation_model.predict(x_train)
    y_test_pred = evaluation_model.predict(x_test)

    y_train_proba = evaluation_model.predict_proba(x_train)
    y_test_proba = evaluation_model.predict_proba(x_test)

    full_pred = service.model.predict(x)
    full_proba = service.model.predict_proba(x)

    result = {
        "status": "ok",
        "evaluation_type": "holdout_split_plus_full_saved_model_check",
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
        "holdout_train_metrics": _evaluate_predictions(
            y_train,
            y_train_pred,
            y_train_proba,
            classes,
        ),
        "holdout_test_metrics": _evaluate_predictions(
            y_test,
            y_test_pred,
            y_test_proba,
            classes,
        ),
        "saved_model_full_dataset_metrics": _evaluate_predictions(
            y,
            full_pred,
            full_proba,
            classes,
        ),
        "interpretation_notes": [
            "Holdout test metrics are the main indicator for model generalization.",
            "Full dataset metrics are only a sanity check for the saved production model.",
            "If full dataset metrics are much higher than holdout metrics, overfitting may be present.",
            "Because the dataset is synthetic/enriched, results should be presented as prototype validation, not final production validation.",
        ],
    }

    with EVALUATION_FILE.open("w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2, default=_json_safe)

    return result


if __name__ == "__main__":
    metrics = evaluate_model()
    print(json.dumps(_compact_summary(metrics), ensure_ascii=False, indent=2, default=_json_safe))