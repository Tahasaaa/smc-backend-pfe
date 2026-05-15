from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.linear_model import SGDClassifier
from sqlalchemy.orm import Session

from app.models import RunbookEntry


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ONLINE_ARTIFACTS_DIR = PROJECT_ROOT / "online_artifacts"

ONLINE_MODEL_FILE = ONLINE_ARTIFACTS_DIR / "online_model.pkl"
ONLINE_METADATA_FILE = ONLINE_ARTIFACTS_DIR / "online_model_metadata.json"

RCA_CLASSES = [
    "Performance",
    "Préventif",
    "Radio Access",
    "Transmission",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_online_dir() -> None:
    ONLINE_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def _safe_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _join_text_parts(parts: List[Any]) -> str:
    clean_parts = []

    for part in parts:
        if part is None:
            continue

        if isinstance(part, list):
            clean_parts.extend(str(x) for x in part if x is not None)
        else:
            clean_parts.append(str(part))

    return " ".join(x.strip() for x in clean_parts if str(x).strip())


def _runbook_to_text(runbook: RunbookEntry) -> str:
    return _join_text_parts(
        [
            runbook.incident_summary,
            runbook.final_conclusion,
            runbook.engineer_notes,
            _safe_list(runbook.checks_json),
            _safe_list(runbook.actions_json),
            _safe_list(runbook.tags_json),
            runbook.site_id,
            runbook.site_name,
            runbook.region,
        ]
    )


def _payload_to_text(payload: Dict[str, Any]) -> str:
    return _join_text_parts(
        [
            payload.get("ticket_text"),
            payload.get("description"),
            payload.get("incident_summary"),
            payload.get("final_conclusion"),
            payload.get("engineer_notes"),
            payload.get("site_id"),
            payload.get("site_name"),
            payload.get("nom_du_site"),
            payload.get("region"),
            payload.get("priorite"),
            payload.get("priorite_texte"),
            payload.get("priority"),
            payload.get("priority_text"),
            payload.get("incident_status"),
            payload.get("etat"),
            payload.get("type_ticket"),
            payload.get("tags"),
            payload.get("checks"),
            payload.get("actions"),
        ]
    )


def _build_vectorizer() -> HashingVectorizer:
    return HashingVectorizer(
        n_features=2**16,
        alternate_sign=False,
        norm="l2",
        lowercase=True,
        ngram_range=(1, 2),
    )


def _build_classifier() -> SGDClassifier:
    return SGDClassifier(
        loss="log_loss",
        penalty="l2",
        alpha=0.0001,
        random_state=42,
        learning_rate="optimal",
    )


def _load_metadata() -> Dict[str, Any]:
    if not ONLINE_METADATA_FILE.exists():
        return {}

    with ONLINE_METADATA_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def _save_metadata(metadata: Dict[str, Any]) -> None:
    _ensure_online_dir()

    with ONLINE_METADATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)


def _load_online_bundle() -> Optional[Dict[str, Any]]:
    if not ONLINE_MODEL_FILE.exists():
        return None

    return joblib.load(ONLINE_MODEL_FILE)


def _save_online_bundle(bundle: Dict[str, Any]) -> None:
    _ensure_online_dir()
    joblib.dump(bundle, ONLINE_MODEL_FILE)


def get_online_training_status() -> Dict[str, Any]:
    metadata = _load_metadata()

    return {
        "status": "ready" if ONLINE_MODEL_FILE.exists() else "not_trained",
        "mode": "experimental_online_learning",
        "model_file": str(ONLINE_MODEL_FILE),
        "metadata_file": str(ONLINE_METADATA_FILE),
        "model_exists": ONLINE_MODEL_FILE.exists(),
        "metadata_exists": ONLINE_METADATA_FILE.exists(),
        "model_size_bytes": ONLINE_MODEL_FILE.stat().st_size if ONLINE_MODEL_FILE.exists() else 0,
        "metadata": metadata,
        "safety_note": (
            "This online model is experimental and does not replace the production "
            "Logistic Regression RCA model stored in artifacts/model.pkl."
        ),
    }


def _query_feedback_runbooks(
    db: Session,
    reusable_only: bool = True,
    approved_family: Optional[str] = None,
    limit: int = 1000,
) -> List[RunbookEntry]:
    query = db.query(RunbookEntry)

    if reusable_only:
        query = query.filter(RunbookEntry.is_reusable == "yes")

    if approved_family:
        query = query.filter(RunbookEntry.approved_family == approved_family)

    return query.order_by(RunbookEntry.created_at.asc()).limit(limit).all()


def _prepare_training_examples(runbooks: List[RunbookEntry]) -> Tuple[List[str], List[str]]:
    texts: List[str] = []
    labels: List[str] = []

    for runbook in runbooks:
        label = runbook.approved_family

        if label not in RCA_CLASSES:
            continue

        text = _runbook_to_text(runbook)

        if not text.strip():
            continue

        texts.append(text)
        labels.append(label)

    return texts, labels


def update_online_model_from_feedback(
    db: Session,
    reusable_only: bool = True,
    approved_family: Optional[str] = None,
    limit: int = 1000,
) -> Dict[str, Any]:
    runbooks = _query_feedback_runbooks(
        db=db,
        reusable_only=reusable_only,
        approved_family=approved_family,
        limit=limit,
    )

    texts, labels = _prepare_training_examples(runbooks)

    if not texts:
        raise ValueError("No valid feedback examples found for online training.")

    bundle = _load_online_bundle()
    metadata = _load_metadata()

    if bundle is None:
        vectorizer = _build_vectorizer()
        classifier = _build_classifier()
        is_new_model = True
    else:
        vectorizer = bundle["vectorizer"]
        classifier = bundle["classifier"]
        is_new_model = False

    x_batch = vectorizer.transform(texts)
    y_batch = np.array(labels, dtype=object)

    if is_new_model:
        classifier.partial_fit(
            x_batch,
            y_batch,
            classes=np.array(RCA_CLASSES, dtype=object),
        )
    else:
        classifier.partial_fit(x_batch, y_batch)

    bundle = {
        "vectorizer": vectorizer,
        "classifier": classifier,
        "classes": RCA_CLASSES,
        "created_for": "experimental_online_rca_learning",
    }

    _save_online_bundle(bundle)

    previous_samples = int(metadata.get("samples_seen_total", 0))
    previous_batches = int(metadata.get("update_batches", 0))

    class_distribution: Dict[str, int] = {}
    for label in labels:
        class_distribution[label] = class_distribution.get(label, 0) + 1

    metadata = {
        "online_model_name": "experimental_sgdclassifier_log_loss",
        "status": "trained",
        "model_type": "SGDClassifier",
        "loss": "log_loss",
        "classes": RCA_CLASSES,
        "last_update_at_utc": _utc_now(),
        "update_batches": previous_batches + 1,
        "samples_seen_total": previous_samples + len(labels),
        "last_batch_size": len(labels),
        "last_batch_class_distribution": class_distribution,
        "feedback_source": "approved reusable runbook_entries",
        "filters": {
            "reusable_only": reusable_only,
            "approved_family": approved_family,
            "limit": limit,
        },
        "safety_note": (
            "This model is experimental. It is updated from human-approved RCA/runbook feedback "
            "and does not replace the production offline-trained RCA model."
        ),
    }

    _save_metadata(metadata)

    return {
        "status": "ok",
        "message": "Experimental online RCA model updated successfully.",
        "is_new_model": is_new_model,
        "batch_size": len(labels),
        "class_distribution": class_distribution,
        "model_file": str(ONLINE_MODEL_FILE),
        "metadata_file": str(ONLINE_METADATA_FILE),
        "metadata": metadata,
    }


def predict_with_online_model(payload: Dict[str, Any], top_k: int = 3) -> Dict[str, Any]:
    bundle = _load_online_bundle()

    if bundle is None:
        raise ValueError("Online model is not trained yet.")

    vectorizer = bundle["vectorizer"]
    classifier = bundle["classifier"]
    classes = list(bundle.get("classes", RCA_CLASSES))

    text = _payload_to_text(payload)

    if not text.strip():
        raise ValueError("Payload does not contain enough text for online prediction.")

    x = vectorizer.transform([text])

    if hasattr(classifier, "predict_proba"):
        probabilities = classifier.predict_proba(x)[0]
    else:
        decision = classifier.decision_function(x)
        probabilities = np.exp(decision) / np.sum(np.exp(decision), axis=1, keepdims=True)
        probabilities = probabilities[0]

    ranked_indices = np.argsort(probabilities)[::-1]
    top_items = []

    for idx in ranked_indices[:top_k]:
        top_items.append(
            {
                "family": classes[idx],
                "probability": round(float(probabilities[idx]), 6),
            }
        )

    predicted_family = top_items[0]["family"]
    confidence = top_items[0]["probability"]

    return {
        "status": "ok",
        "mode": "experimental_online_model",
        "predicted_family": predicted_family,
        "confidence": confidence,
        "top_hypotheses": top_items,
        "input_text_preview": text[:500],
        "note": (
            "This prediction comes from the experimental online SGDClassifier model, "
            "not from the production RCA Logistic Regression model."
        ),
    }