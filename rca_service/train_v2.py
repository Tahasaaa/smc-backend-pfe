from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import joblib

from app.services.ml_service import RCAModelService, DEFAULT_TARGET_COLUMN


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"

REQUIRED_DATA_FILES = [
    "master_sites_corrected_synthetic.csv",
    "engineering_parameters_corrected_synthetic.csv",
    "tickets_radio_synthetic_linked.csv",
]

ARTIFACT_FILENAMES = [
    "model.pkl",
    "feature_columns.json",
    "numeric_columns.json",
    "categorical_columns.json",
    "all_null_columns.json",
    "model_metadata.json",
]


def utc_now_label() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def validate_data_files(data_dir: Path) -> None:
    missing = [
        filename
        for filename in REQUIRED_DATA_FILES
        if not (data_dir / filename).exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Missing required RCA training data files: "
            + ", ".join(missing)
            + f" in {data_dir}"
        )


def backup_existing_artifacts(artifacts_dir: Path) -> Path | None:
    existing_files = [
        artifacts_dir / filename
        for filename in ARTIFACT_FILENAMES
        if (artifacts_dir / filename).exists()
    ]

    if not existing_files:
        return None

    backup_dir = artifacts_dir.parent / f"artifacts_backup_{utc_now_label()}"
    ensure_dir(backup_dir)

    for file_path in existing_files:
        shutil.copy2(file_path, backup_dir / file_path.name)

    return backup_dir


def save_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def get_classifier_classes(service: RCAModelService) -> List[str]:
    if service.model is None:
        return []

    classifier = service.model.named_steps.get("classifier")

    if classifier is not None and hasattr(classifier, "classes_"):
        return classifier.classes_.tolist()

    return []


def build_metadata(
    service: RCAModelService,
    train_info: Dict[str, Any],
    data_dir: Path,
    artifacts_dir: Path,
    model_file: Path,
) -> Dict[str, Any]:
    classes = get_classifier_classes(service)

    metadata = {
        "model_name": "v2_rca_logistic_regression",
        "model_version": f"v2-{utc_now_label()}",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_column": service.target_column,
        "rows": train_info.get("rows"),
        "classes": classes,
        "feature_count": len(service.training_feature_columns),
        "numeric_feature_count": len(service.numeric_columns),
        "categorical_feature_count": len(service.categorical_columns),
        "text_column": service.text_column,
        "all_null_columns": service.all_null_columns,
        "train_info": train_info,
        "artifacts": {
            "artifacts_dir": str(artifacts_dir),
            "model": model_file.name,
            "feature_columns": "feature_columns.json",
            "numeric_columns": "numeric_columns.json",
            "categorical_columns": "categorical_columns.json",
            "all_null_columns": "all_null_columns.json",
            "metadata": "model_metadata.json",
        },
        "data": {
            "data_dir": str(data_dir),
            "sources": REQUIRED_DATA_FILES,
        },
        "notes": [
            "Offline training pipeline for the RCA V2 service.",
            "The FastAPI service loads these artifacts at startup.",
            "Human-approved RCA/runbook entries can be used later as feedback for retraining.",
            "True online incremental learning is planned as a future extension using SGDClassifier(log_loss).",
        ],
    }

    return metadata


def train_and_save(
    data_dir: Path = DEFAULT_DATA_DIR,
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
    create_backup: bool = True,
) -> Dict[str, Any]:
    data_dir = data_dir.resolve()
    artifacts_dir = artifacts_dir.resolve()

    validate_data_files(data_dir)
    ensure_dir(artifacts_dir)

    backup_dir = None
    if create_backup:
        backup_dir = backup_existing_artifacts(artifacts_dir)

    model_file = artifacts_dir / "model.pkl"
    feature_columns_file = artifacts_dir / "feature_columns.json"
    numeric_columns_file = artifacts_dir / "numeric_columns.json"
    categorical_columns_file = artifacts_dir / "categorical_columns.json"
    all_null_columns_file = artifacts_dir / "all_null_columns.json"
    metadata_file = artifacts_dir / "model_metadata.json"

    service = RCAModelService(
        data_dir=data_dir,
        target_column=DEFAULT_TARGET_COLUMN,
    )

    train_info = service.train()

    if service.model is None:
        raise RuntimeError("Training completed but no model was produced.")

    joblib.dump(service.model, model_file)

    save_json(feature_columns_file, service.training_feature_columns)
    save_json(numeric_columns_file, service.numeric_columns)
    save_json(categorical_columns_file, service.categorical_columns)
    save_json(all_null_columns_file, service.all_null_columns)

    metadata = build_metadata(
        service=service,
        train_info=train_info,
        data_dir=data_dir,
        artifacts_dir=artifacts_dir,
        model_file=model_file,
    )
    save_json(metadata_file, metadata)

    result = {
        "status": "ok",
        "message": "V2 RCA model trained and artifacts saved successfully.",
        "data_dir": str(data_dir),
        "artifacts_dir": str(artifacts_dir),
        "backup_dir": str(backup_dir) if backup_dir else None,
        "model_file": str(model_file),
        "rows": train_info.get("rows"),
        "classes": metadata["classes"],
        "feature_count": len(service.training_feature_columns),
        "numeric_feature_count": len(service.numeric_columns),
        "categorical_feature_count": len(service.categorical_columns),
        "all_null_columns": service.all_null_columns,
        "metadata_file": str(metadata_file),
    }

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline training pipeline for the V2 RCA model."
    )

    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help="Directory containing RCA CSV training files.",
    )

    parser.add_argument(
        "--artifacts-dir",
        default=str(DEFAULT_ARTIFACTS_DIR),
        help="Directory where trained model artifacts will be saved.",
    )

    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Disable backup of existing artifacts before overwriting.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    result = train_and_save(
        data_dir=Path(args.data_dir),
        artifacts_dir=Path(args.artifacts_dir),
        create_backup=not args.no_backup,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
