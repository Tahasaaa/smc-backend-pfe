from __future__ import annotations

import importlib.util
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.services.ml_service import DEFAULT_TARGET_COLUMN, get_service, load_training_dataframe


TARGET_COLUMNS = {
    DEFAULT_TARGET_COLUMN,
    "famille_de_problemes",
    "rca_family",
    "family",
    "label",
    "target",
}


def _package_installed(package_name: str) -> bool:
    return importlib.util.find_spec(package_name) is not None


def explainability_package_status() -> Dict[str, bool]:
    return {
        "lime_installed": _package_installed("lime"),
        "shap_installed": _package_installed("shap"),
    }


def _safe_json_value(value: Any) -> Any:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, np.generic):
        return value.item()

    return value


def _safe_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {key: _safe_json_value(value) for key, value in payload.items()}


def _clean_feature_name(name: str) -> str:
    cleaned = str(name)

    for prefix in [
        "num__",
        "cat__",
        "text__",
        "remainder__",
        "onehot__",
        "tfidf__",
        "bow__",
    ]:
        cleaned = cleaned.replace(prefix, "")

    return cleaned


def _load_ticket_payload(ticket_id: str) -> Dict[str, Any]:
    df = load_training_dataframe()

    if "ticket_id" not in df.columns:
        raise ValueError("RCA training dataframe does not contain ticket_id.")

    matches = df.loc[df["ticket_id"].astype(str) == str(ticket_id)]

    if matches.empty:
        raise ValueError(f"Ticket '{ticket_id}' not found in RCA dataset.")

    row = matches.iloc[0].copy()

    drop_columns = [col for col in TARGET_COLUMNS if col in row.index]

    payload = row.drop(labels=drop_columns, errors="ignore").to_dict()
    payload = _safe_payload(payload)

    payload["ticket_id"] = payload.get("ticket_id") or ticket_id
    payload["ticket_text"] = (
        payload.get("ticket_text")
        or payload.get("description")
        or f"RCA dataset ticket {ticket_id}"
    )
    payload["site_name"] = (
        payload.get("site_name")
        or payload.get("nom_du_site")
        or payload.get("site_id")
    )
    payload["nom_du_site"] = (
        payload.get("nom_du_site")
        or payload.get("site_name")
        or payload.get("site_id")
    )
    payload["region"] = payload.get("region") or str(
        payload.get("site_id") or ""
    ).split("_")[0]

    return payload


def _candidate_explanation_features(payload: Dict[str, Any]) -> List[str]:
    preferred = [
        "ticket_text",
        "priorite",
        "priorite_texte",
        "etat",
        "type_ticket",
        "incident_status",
        "site_id",
        "nom_du_site",
        "region",
        "kpi_3g_cssr_ps",
        "kpi_3g_shosr",
        "kpi_3g_throughput",
        "kpi_3g_dropcall_cs",
        "kpi_3g_cs_rab_setup_sr",
        "kpi_3g_cs_interrat_ho_sr",
        "incident_potential",
        "matched_incident_count",
        "incident_mapping_confidence",
        "worst_priority_code",
        "engineering_record_count",
        "frequency_band",
        "actual_load_dl",
        "max_power",
        "pilot_power",
        "azimuth",
        "antheight",
        "mechtilt",
        "electilt",
    ]

    existing = [key for key in preferred if key in payload and payload.get(key) is not None]

    if len(existing) >= 8:
        return existing

    extra = [
        key
        for key, value in payload.items()
        if key not in existing
        and key not in {"ticket_id"}
        and value is not None
    ]

    return (existing + extra)[:40]


def _neutral_value(feature: str, original_value: Any, df: pd.DataFrame) -> Any:
    if feature in df.columns and pd.api.types.is_numeric_dtype(df[feature]):
        median = pd.to_numeric(df[feature], errors="coerce").median()
        if not pd.isna(median):
            return float(median)
        return 0.0

    if isinstance(original_value, (int, float, np.number)):
        return 0.0

    if "text" in feature.lower() or "description" in feature.lower():
        return ""

    return ""


def _build_lime_text_explanation(
    payload: Dict[str, Any],
    predicted_family: str,
    top_n: int,
) -> Dict[str, Any]:
    status = explainability_package_status()

    if not status["lime_installed"]:
        return {
            "available": False,
            "method": "official_lime_text",
            "reason": "lime package is not installed.",
            "items": [],
        }

    try:
        from lime.lime_text import LimeTextExplainer
    except Exception as exc:
        return {
            "available": False,
            "method": "official_lime_text",
            "reason": f"lime import failed: {exc}",
            "items": [],
        }

    service = get_service()
    base_payload = dict(payload)
    original_text = str(base_payload.get("ticket_text") or "")

    if not original_text.strip():
        return {
            "available": False,
            "method": "official_lime_text",
            "reason": "ticket_text is empty.",
            "items": [],
        }

    classifier = service.model.named_steps.get("classifier")
    if classifier is not None and hasattr(classifier, "classes_"):
        classes = [str(x) for x in classifier.classes_.tolist()]
    else:
        classes = ["Performance", "Préventif", "Radio Access", "Transmission"]

    def classifier_fn(texts: List[str]) -> np.ndarray:
        rows = []

        for text in texts:
            row_payload = dict(base_payload)
            row_payload["ticket_text"] = text

            prediction = service.predict(row_payload, top_k=len(classes))

            probability_by_class = {
                item["family"]: float(item["probability"])
                for item in prediction.get("top_hypotheses", [])
            }

            rows.append(
                [
                    probability_by_class.get(class_name, 0.0)
                    for class_name in classes
                ]
            )

        return np.array(rows)

    try:
        explainer = LimeTextExplainer(class_names=classes)
        explanation = explainer.explain_instance(
            original_text,
            classifier_fn,
            num_features=top_n,
            labels=[classes.index(predicted_family)] if predicted_family in classes else None,
        )

        label_index = classes.index(predicted_family) if predicted_family in classes else explanation.available_labels()[0]

        items = [
            {
                "token_or_phrase": feature,
                "weight": round(float(weight), 6),
                "direction": "supports_prediction" if weight > 0 else "opposes_prediction",
            }
            for feature, weight in explanation.as_list(label=label_index)
        ]

        return {
            "available": True,
            "method": "official_lime_text",
            "explained_class": predicted_family,
            "class_names": classes,
            "items": items,
            "note": (
                "This official LIME explanation focuses on the ticket text. "
                "Structured KPI/metadata influence is still covered by the perturbation explanation."
            ),
        }

    except Exception as exc:
        return {
            "available": False,
            "method": "official_lime_text",
            "reason": f"LIME explanation failed: {exc}",
            "items": [],
        }


def build_local_explanation(ticket_id: str, top_n: int = 10) -> Dict[str, Any]:
    service = get_service()

    if not service.is_trained or service.model is None:
        raise RuntimeError("Model artifacts are not loaded.")

    df = load_training_dataframe()
    payload = _load_ticket_payload(ticket_id)

    prediction = service.predict(payload, top_k=3)
    predicted_family = prediction["predicted_family"]
    base_confidence = float(prediction["confidence"])

    candidates = _candidate_explanation_features(payload)
    feature_effects: List[Dict[str, Any]] = []

    for feature in candidates:
        if feature not in payload:
            continue

        original_value = payload.get(feature)
        perturbed_payload = dict(payload)
        perturbed_value = _neutral_value(feature, original_value, df)
        perturbed_payload[feature] = perturbed_value

        try:
            perturbed_prediction = service.predict(perturbed_payload, top_k=3)
        except Exception:
            continue

        new_probability = 0.0
        for item in perturbed_prediction.get("top_hypotheses", []):
            if item.get("family") == predicted_family:
                new_probability = float(item.get("probability", 0.0))
                break

        delta = base_confidence - new_probability

        feature_effects.append(
            {
                "feature": feature,
                "original_value": _safe_json_value(original_value),
                "perturbed_value": _safe_json_value(perturbed_value),
                "predicted_family_probability_before": round(base_confidence, 6),
                "predicted_family_probability_after": round(new_probability, 6),
                "importance_delta": round(delta, 6),
                "effect": "supports_prediction" if delta > 0 else "opposes_or_neutral",
            }
        )

    feature_effects = sorted(
        feature_effects,
        key=lambda item: abs(float(item["importance_delta"])),
        reverse=True,
    )[:top_n]

    lime_text_explanation = _build_lime_text_explanation(
        payload=payload,
        predicted_family=predicted_family,
        top_n=top_n,
    )

    return {
        "ticket_id": ticket_id,
        "method": "hybrid_local_explainability",
        "note": (
            "This endpoint combines official LIME text explanation when available "
            "with safe perturbation-based explanation for structured RCA features."
        ),
        "package_status": explainability_package_status(),
        "predicted_family": predicted_family,
        "confidence": base_confidence,
        "top_hypotheses": prediction.get("top_hypotheses", []),
        "lime_text_explanation": lime_text_explanation,
        "structured_feature_perturbation": {
            "method": "local_perturbation_lime_style",
            "top_features": feature_effects,
        },
    }


def _extract_linear_feature_importance() -> Tuple[List[str], Optional[np.ndarray], List[str]]:
    service = get_service()

    if not service.is_trained or service.model is None:
        raise RuntimeError("Model artifacts are not loaded.")

    classifier = service.model.named_steps.get("classifier")
    preprocessor = service.model.named_steps.get("preprocessor")

    if classifier is None or not hasattr(classifier, "coef_"):
        return [], None, []

    classes = classifier.classes_.tolist() if hasattr(classifier, "classes_") else []
    coefs = classifier.coef_

    feature_names: List[str] = []

    if preprocessor is not None and hasattr(preprocessor, "get_feature_names_out"):
        try:
            feature_names = [
                _clean_feature_name(name)
                for name in preprocessor.get_feature_names_out().tolist()
            ]
        except Exception:
            feature_names = []

    if not feature_names:
        feature_count = coefs.shape[1] if len(coefs.shape) == 2 else len(coefs)
        feature_names = [f"feature_{idx}" for idx in range(feature_count)]

    return feature_names, coefs, classes


def build_global_explanation(top_n: int = 25) -> Dict[str, Any]:
    feature_names, coefs, classes = _extract_linear_feature_importance()
    package_status = explainability_package_status()

    if coefs is None:
        return {
            "method": "global_explanation_unavailable",
            "note": "The current classifier does not expose linear coefficients.",
            "package_status": package_status,
            "items": [],
        }

    if coefs.ndim == 1:
        importance = np.abs(coefs)
    else:
        importance = np.mean(np.abs(coefs), axis=0)

    items = []
    for idx, value in enumerate(importance):
        feature_name = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"
        items.append(
            {
                "feature": feature_name,
                "importance": round(float(value), 6),
            }
        )

    items = sorted(items, key=lambda item: item["importance"], reverse=True)[:top_n]

    by_class: Dict[str, List[Dict[str, Any]]] = {}

    if coefs.ndim == 2 and classes:
        for class_index, class_name in enumerate(classes):
            class_items = []
            class_coef = coefs[class_index]

            for idx, value in enumerate(class_coef):
                feature_name = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"
                class_items.append(
                    {
                        "feature": feature_name,
                        "coefficient": round(float(value), 6),
                        "direction": "supports_class" if value > 0 else "opposes_class",
                        "absolute_importance": round(abs(float(value)), 6),
                    }
                )

            by_class[str(class_name)] = sorted(
                class_items,
                key=lambda item: item["absolute_importance"],
                reverse=True,
            )[:top_n]

    shap_note = (
        "The shap package is installed. For this production API, global explanation uses "
        "Logistic Regression coefficients as a stable SHAP-style baseline for linear models. "
        "A full SHAP value endpoint can be added later if needed."
        if package_status["shap_installed"]
        else "The shap package is not installed; coefficient-based global explanation is used."
    )

    return {
        "method": "global_linear_importance_shap_style",
        "note": shap_note,
        "package_status": package_status,
        "classes": classes,
        "top_global_features": items,
        "top_features_by_class": by_class,
    }