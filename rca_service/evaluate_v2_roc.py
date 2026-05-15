from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import auc, roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import label_binarize

from app.services.ml_service import (
    DEFAULT_TARGET_COLUMN,
    get_service,
    load_model_artifacts,
    load_training_dataframe,
)


PROJECT_ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
ROC_EVALUATION_FILE = ARTIFACTS_DIR / "model_roc_evaluation.json"
ROC_CURVE_IMAGE_FILE = ARTIFACTS_DIR / "model_roc_curves.png"


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


def _safe_curve_points(fpr, tpr, max_points: int = 30) -> List[Dict[str, float]]:
    if len(fpr) <= max_points:
        indices = list(range(len(fpr)))
    else:
        indices = np.linspace(0, len(fpr) - 1, max_points).astype(int).tolist()

    return [
        {
            "fpr": round(float(fpr[idx]), 6),
            "tpr": round(float(tpr[idx]), 6),
        }
        for idx in indices
    ]


def _try_save_roc_plot(
    curves: Dict[str, Dict[str, Any]],
    macro_auc: float,
    output_file: Path,
) -> bool:
    try:
        import matplotlib.pyplot as plt

        plt.figure(figsize=(9, 7))

        for class_name, payload in curves.items():
            fpr = payload["fpr_raw"]
            tpr = payload["tpr_raw"]
            roc_auc = payload["auc"]

            plt.plot(
                fpr,
                tpr,
                label=f"{class_name} AUC={roc_auc:.4f}",
            )

        plt.plot([0, 1], [0, 1], linestyle="--", label="Random classifier")
        plt.xlabel("False Positive Rate")
        plt.ylabel("True Positive Rate")
        plt.title(f"Multiclass ROC Curves - RCA Model | Macro AUC={macro_auc:.4f}")
        plt.legend(loc="lower right")
        plt.tight_layout()
        plt.savefig(output_file, dpi=160)
        plt.close()

        return True

    except Exception:
        return False


def evaluate_roc(
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

    y_score = evaluation_model.predict_proba(x_test)
    y_test_bin = label_binarize(y_test, classes=classes)

    per_class_auc: Dict[str, float] = {}
    roc_curves: Dict[str, Dict[str, Any]] = {}
    raw_curves_for_plot: Dict[str, Dict[str, Any]] = {}

    for class_index, class_name in enumerate(classes):
        fpr, tpr, thresholds = roc_curve(y_test_bin[:, class_index], y_score[:, class_index])
        class_auc = auc(fpr, tpr)

        per_class_auc[class_name] = round(float(class_auc), 6)

        roc_curves[class_name] = {
            "auc": round(float(class_auc), 6),
            "curve_points_sampled": _safe_curve_points(fpr, tpr, max_points=30),
            "threshold_count": int(len(thresholds)),
        }

        raw_curves_for_plot[class_name] = {
            "fpr_raw": fpr,
            "tpr_raw": tpr,
            "auc": float(class_auc),
        }

    macro_ovr_auc = roc_auc_score(
        y_test,
        y_score,
        labels=classes,
        multi_class="ovr",
        average="macro",
    )

    weighted_ovr_auc = roc_auc_score(
        y_test,
        y_score,
        labels=classes,
        multi_class="ovr",
        average="weighted",
    )

    macro_ovo_auc = roc_auc_score(
        y_test,
        y_score,
        labels=classes,
        multi_class="ovo",
        average="macro",
    )

    weighted_ovo_auc = roc_auc_score(
        y_test,
        y_score,
        labels=classes,
        multi_class="ovo",
        average="weighted",
    )

    y_test_bin_flat = y_test_bin.ravel()
    y_score_flat = y_score.ravel()

    micro_fpr, micro_tpr, micro_thresholds = roc_curve(y_test_bin_flat, y_score_flat)
    micro_auc = auc(micro_fpr, micro_tpr)

    plot_saved = _try_save_roc_plot(
        curves=raw_curves_for_plot,
        macro_auc=float(macro_ovr_auc),
        output_file=ROC_CURVE_IMAGE_FILE,
    )

    result = {
        "status": "ok",
        "evaluation_type": "multiclass_roc_auc_holdout",
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
        "roc_auc": {
            "macro_ovr": round(float(macro_ovr_auc), 6),
            "weighted_ovr": round(float(weighted_ovr_auc), 6),
            "macro_ovo": round(float(macro_ovo_auc), 6),
            "weighted_ovo": round(float(weighted_ovo_auc), 6),
            "micro": round(float(micro_auc), 6),
            "per_class": per_class_auc,
        },
        "roc_curves": roc_curves,
        "micro_curve": {
            "auc": round(float(micro_auc), 6),
            "curve_points_sampled": _safe_curve_points(micro_fpr, micro_tpr, max_points=30),
            "threshold_count": int(len(micro_thresholds)),
        },
        "artifacts": {
            "roc_evaluation_file": str(ROC_EVALUATION_FILE),
            "roc_curve_image_file": str(ROC_CURVE_IMAGE_FILE),
            "roc_curve_image_saved": plot_saved,
        },
        "interpretation_notes": [
            "ROC AUC evaluates how well the model separates each RCA family from the others.",
            "For multiclass classification, One-vs-Rest and One-vs-One ROC AUC are reported.",
            "AUC close to 1.0 means excellent separability on the evaluated dataset.",
            "If AUC is perfect, it should be interpreted carefully because the dataset may be synthetic, enriched, or strongly separable.",
        ],
    }

    with ROC_EVALUATION_FILE.open("w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2, default=_json_safe)

    return result


def _compact_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": result["status"],
        "evaluated_at_utc": result["evaluated_at_utc"],
        "dataset": result["dataset"],
        "split": result["split"],
        "roc_auc": result["roc_auc"],
        "artifacts": result["artifacts"],
    }


if __name__ == "__main__":
    output = evaluate_roc()
    print(json.dumps(_compact_summary(output), ensure_ascii=False, indent=2, default=_json_safe))