from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.services.data_pipeline import (
    build_incident_dataset,
    load_raw_data,
    split_features_target,
)

DEFAULT_TARGET_COLUMN = "famille_de_problemes"

BASE_DROP_COLUMNS = {
    "ticket_id",
    "site_id",
    DEFAULT_TARGET_COLUMN,
}

TEXT_SOURCE_CANDIDATES = [
    "ticket_text",
    "origine",
    "etat",
    "type_ticket",
    "priorite_texte",
    "nom_du_site",
    "site_name",
    "region",
    "incident_status",
    "worst_priority_text",
    "incident_match_source",
    "mapping_source",
    "frequency_band",
]

DATE_COLUMN_PREFIXES = ("date_",)


class RCAModelService:
    def __init__(
        self,
        data_dir: Optional[str | Path] = None,
        target_column: str = DEFAULT_TARGET_COLUMN,
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir else None
        self.target_column = target_column

        self.model: Optional[Pipeline] = None
        self.training_feature_columns: List[str] = []
        self.numeric_columns: List[str] = []
        self.categorical_columns: List[str] = []
        self.all_null_columns: List[str] = []
        self.text_column: str = "combined_text"
        self.is_trained: bool = False

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    def _project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _artifacts_dir(self) -> Path:
        return self._project_root() / "artifacts"

    def _model_file(self) -> Path:
        return self._artifacts_dir() / "model.pkl"

    def _feature_columns_file(self) -> Path:
        return self._artifacts_dir() / "feature_columns.json"

    def _numeric_columns_file(self) -> Path:
        return self._artifacts_dir() / "numeric_columns.json"

    def _categorical_columns_file(self) -> Path:
        return self._artifacts_dir() / "categorical_columns.json"

    def _all_null_columns_file(self) -> Path:
        return self._artifacts_dir() / "all_null_columns.json"

    def _metadata_file(self) -> Path:
        return self._artifacts_dir() / "model_metadata.json"

    # ------------------------------------------------------------------
    # Artifact loading
    # ------------------------------------------------------------------

    def load_artifacts(self) -> Dict[str, Any]:
        model_path = self._model_file()
        feature_columns_path = self._feature_columns_file()
        numeric_columns_path = self._numeric_columns_file()
        categorical_columns_path = self._categorical_columns_file()
        all_null_columns_path = self._all_null_columns_file()
        metadata_path = self._metadata_file()

        required_files = [
            model_path,
            feature_columns_path,
            numeric_columns_path,
            categorical_columns_path,
            all_null_columns_path,
            metadata_path,
        ]

        missing = [str(p) for p in required_files if not p.exists()]
        if missing:
            raise FileNotFoundError(
                f"Missing required model artifacts: {missing}. "
                f"Run 'python train_v2.py' first."
            )

        self.model = joblib.load(model_path)

        with feature_columns_path.open("r", encoding="utf-8") as f:
            self.training_feature_columns = json.load(f)

        with numeric_columns_path.open("r", encoding="utf-8") as f:
            self.numeric_columns = json.load(f)

        with categorical_columns_path.open("r", encoding="utf-8") as f:
            self.categorical_columns = json.load(f)

        with all_null_columns_path.open("r", encoding="utf-8") as f:
            self.all_null_columns = json.load(f)

        with metadata_path.open("r", encoding="utf-8") as f:
            metadata = json.load(f)

        self.text_column = metadata.get("text_column", "combined_text")
        self.target_column = metadata.get("target_column", self.target_column)
        self.is_trained = True

        return {
            "status": "loaded",
            "model_file": str(model_path),
            "feature_count": len(self.training_feature_columns),
            "classes": metadata.get("classes", []),
            "trained_at_utc": metadata.get("trained_at_utc"),
        }

    # ------------------------------------------------------------------
    # Public training data API
    # ------------------------------------------------------------------

    def load_training_dataframe(self) -> pd.DataFrame:
        raw_data = load_raw_data(self.data_dir)
        incident_df = build_incident_dataset(raw_data)
        return incident_df

    def get_training_data(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
        incident_df = self.load_training_dataframe()

        if self.target_column not in incident_df.columns:
            raise ValueError(
                f"Target column '{self.target_column}' not found. "
                f"Available columns: {list(incident_df.columns)}"
            )

        X_raw, y = split_features_target(incident_df, target_column=self.target_column)
        X = self._prepare_features_for_model(X_raw, fit_mode=True)

        valid_mask = y.notna()
        X = X.loc[valid_mask].reset_index(drop=True)
        y = y.loc[valid_mask].reset_index(drop=True)
        incident_df = incident_df.loc[valid_mask].reset_index(drop=True)

        self.all_null_columns = [col for col in X.columns if X[col].isna().all()]
        X = X.drop(columns=self.all_null_columns, errors="ignore")

        return incident_df, X, y

    def train(self) -> Dict[str, Any]:
        incident_df, X, y = self.get_training_data()

        self.training_feature_columns = list(X.columns)

        self.numeric_columns = X.select_dtypes(include=["number", "bool"]).columns.tolist()
        self.categorical_columns = [
            col for col in X.columns
            if col not in self.numeric_columns and col != self.text_column
        ]

        preprocessor = self._build_preprocessor()
        classifier = LogisticRegression(max_iter=2000)

        self.model = Pipeline(
            steps=[
                ("preprocessor", preprocessor),
                ("classifier", classifier),
            ]
        )

        self.model.fit(X, y)
        self.is_trained = True

        classes = []
        if hasattr(self.model.named_steps["classifier"], "classes_"):
            classes = self.model.named_steps["classifier"].classes_.tolist()

        return {
            "status": "trained",
            "rows": int(len(incident_df)),
            "feature_columns": self.training_feature_columns,
            "numeric_feature_count": len(self.numeric_columns),
            "categorical_feature_count": len(self.categorical_columns),
            "classes": classes,
        }

    # ------------------------------------------------------------------
    # Public prediction API
    # ------------------------------------------------------------------

    def predict(self, incident_payload: Dict[str, Any], top_k: int = 3) -> Dict[str, Any]:
        if not self.is_trained or self.model is None:
            raise RuntimeError(
                "Model is not loaded or trained yet. "
                "Call load_artifacts() or train() first."
            )

        input_df = pd.DataFrame([incident_payload])
        input_df = self._prepare_features_for_model(input_df, fit_mode=False)
        input_df = input_df.drop(columns=self.all_null_columns, errors="ignore")
        input_df = self._align_inference_frame(input_df)

        probabilities = self.model.predict_proba(input_df)[0]
        prediction = self.model.predict(input_df)[0]

        classifier = self.model.named_steps["classifier"]
        classes = classifier.classes_

        top_hypotheses = self._build_top_hypotheses(
            classes=classes,
            probabilities=probabilities,
            top_k=top_k,
        )

        confidence = float(max(probabilities)) if len(probabilities) else 0.0

        return {
            "predicted_family": prediction,
            "confidence": round(confidence, 4),
            "top_hypotheses": top_hypotheses,
        }

    def predict_from_dataframe_row(self, row: pd.Series, top_k: int = 3) -> Dict[str, Any]:
        payload = row.to_dict()
        return self.predict(payload, top_k=top_k)

    def predict_existing_ticket(self, ticket_id: str, top_k: int = 3) -> Dict[str, Any]:
        if not self.is_trained or self.model is None:
            raise RuntimeError(
                "Model is not loaded or trained yet. "
                "Call load_artifacts() or train() first."
            )

        incident_df = self.load_training_dataframe()

        if "ticket_id" not in incident_df.columns:
            raise ValueError("incident dataframe does not contain 'ticket_id'")

        matches = incident_df.loc[incident_df["ticket_id"] == ticket_id]
        if matches.empty:
            raise ValueError(f"Ticket '{ticket_id}' not found in incident dataset.")

        row = matches.iloc[0].copy()
        actual_family = row.get(self.target_column)
        features_only = row.drop(labels=[self.target_column], errors="ignore")

        prediction = self.predict_from_dataframe_row(features_only, top_k=top_k)
        prediction["ticket_id"] = ticket_id
        prediction["actual_family"] = actual_family

        return prediction

    # ------------------------------------------------------------------
    # Internal preprocessing
    # ------------------------------------------------------------------

    def _prepare_features_for_model(self, df: pd.DataFrame, fit_mode: bool) -> pd.DataFrame:
        frame = df.copy()

        drop_cols = [col for col in BASE_DROP_COLUMNS if col in frame.columns]
        frame = frame.drop(columns=drop_cols, errors="ignore")

        frame = self._expand_date_columns(frame)
        frame[self.text_column] = self._build_combined_text(frame)

        return frame

    def _expand_date_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        frame = df.copy()

        date_cols = [
            col for col in frame.columns
            if col.startswith(DATE_COLUMN_PREFIXES)
        ]

        for col in date_cols:
            parsed = pd.to_datetime(frame[col], dayfirst=True, errors="coerce")

            frame[f"{col}_year"] = parsed.dt.year
            frame[f"{col}_month"] = parsed.dt.month
            frame[f"{col}_day"] = parsed.dt.day
            frame[f"{col}_hour"] = parsed.dt.hour
            frame[f"{col}_minute"] = parsed.dt.minute
            frame[f"{col}_weekday"] = parsed.dt.weekday

        if "date_debut" in frame.columns and "date_d_acquittement" in frame.columns:
            debut = pd.to_datetime(frame["date_debut"], dayfirst=True, errors="coerce")
            acquittement = pd.to_datetime(frame["date_d_acquittement"], dayfirst=True, errors="coerce")
            frame["minutes_to_ack"] = (acquittement - debut).dt.total_seconds() / 60.0

        if "date_debut" in frame.columns and "date_de_reparation" in frame.columns:
            debut = pd.to_datetime(frame["date_debut"], dayfirst=True, errors="coerce")
            reparation = pd.to_datetime(frame["date_de_reparation"], dayfirst=True, errors="coerce")
            frame["minutes_to_repair"] = (reparation - debut).dt.total_seconds() / 60.0

        if "date_debut" in frame.columns and "date_de_cloture" in frame.columns:
            debut = pd.to_datetime(frame["date_debut"], dayfirst=True, errors="coerce")
            cloture = pd.to_datetime(frame["date_de_cloture"], dayfirst=True, errors="coerce")
            frame["minutes_to_close"] = (cloture - debut).dt.total_seconds() / 60.0

        frame = frame.drop(columns=date_cols, errors="ignore")

        return frame

    def _build_combined_text(self, df: pd.DataFrame) -> pd.Series:
        available_text_cols = [col for col in TEXT_SOURCE_CANDIDATES if col in df.columns]

        if not available_text_cols:
            return pd.Series([""] * len(df), index=df.index)

        combined = (
            df[available_text_cols]
            .fillna("")
            .astype(str)
            .agg(" ".join, axis=1)
            .str.strip()
        )

        return combined

    def _build_preprocessor(self) -> ColumnTransformer:
        transformers = []

        if self.text_column in self.training_feature_columns:
            transformers.append(
                (
                    "text",
                    TfidfVectorizer(
                        max_features=5000,
                        ngram_range=(1, 2),
                        min_df=2,
                    ),
                    self.text_column,
                )
            )

        if self.numeric_columns:
            transformers.append(
                (
                    "num",
                    Pipeline(
                        steps=[
                            ("imputer", SimpleImputer(strategy="median")),
                            ("scaler", StandardScaler()),
                        ]
                    ),
                    self.numeric_columns,
                )
            )

        if self.categorical_columns:
            transformers.append(
                (
                    "cat",
                    Pipeline(
                        steps=[
                            ("imputer", SimpleImputer(strategy="most_frequent")),
                            ("onehot", OneHotEncoder(handle_unknown="ignore")),
                        ]
                    ),
                    self.categorical_columns,
                )
            )

        return ColumnTransformer(
            transformers=transformers,
            remainder="drop",
        )

    def _align_inference_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.training_feature_columns:
            raise RuntimeError("training_feature_columns are not initialized.")

        frame = df.copy()

        for col in self.training_feature_columns:
            if col not in frame.columns:
                frame[col] = np.nan

        frame = frame[self.training_feature_columns]
        frame = frame.replace({pd.NA: np.nan})

        for col in self.numeric_columns:
            if col in frame.columns:
                frame[col] = pd.to_numeric(frame[col], errors="coerce")

        for col in self.categorical_columns:
            if col in frame.columns:
                frame[col] = frame[col].fillna("").astype(str)

        if self.text_column in frame.columns:
            frame[self.text_column] = frame[self.text_column].fillna("").astype(str)

        return frame

    def _build_top_hypotheses(
        self,
        classes,
        probabilities,
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        pairs = list(zip(classes, probabilities))
        pairs = sorted(pairs, key=lambda x: x[1], reverse=True)[:top_k]

        return [
            {
                "family": family,
                "probability": round(float(prob), 4),
            }
            for family, prob in pairs
        ]


_default_service: Optional[RCAModelService] = None


def get_service(
    data_dir: Optional[str | Path] = None,
    target_column: str = DEFAULT_TARGET_COLUMN,
) -> RCAModelService:
    global _default_service

    if _default_service is None:
        _default_service = RCAModelService(
            data_dir=data_dir,
            target_column=target_column,
        )

    return _default_service


def load_training_dataframe(data_dir: Optional[str | Path] = None) -> pd.DataFrame:
    service = get_service(data_dir=data_dir)
    return service.load_training_dataframe()


def get_training_data(
    data_dir: Optional[str | Path] = None,
    target_column: str = DEFAULT_TARGET_COLUMN,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    service = get_service(data_dir=data_dir, target_column=target_column)
    return service.get_training_data()


def train_model(
    data_dir: Optional[str | Path] = None,
    target_column: str = DEFAULT_TARGET_COLUMN,
) -> Dict[str, Any]:
    service = get_service(data_dir=data_dir, target_column=target_column)
    return service.train()


def load_model_artifacts() -> Dict[str, Any]:
    service = get_service()
    return service.load_artifacts()


def predict_incident(
    incident_payload: Dict[str, Any],
    top_k: int = 3,
) -> Dict[str, Any]:
    service = get_service()
    return service.predict(incident_payload, top_k=top_k)