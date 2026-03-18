# P21 — ML Prediction Agent + MCP

## Objective
Build `ml-predict-mcp`: an MCP server providing XGBoost-based price direction prediction at T+1, T+3, T+5 horizons. Includes SHAP explainability, model versioning in S3, and a SageMaker training pipeline. Also build the ML Prediction Agent handler in the agents repo. Updates the composite score formula to include ML weight: gap(35%) + sentiment(25%) + technical(20%) + ml(20%).

## Plane Tickets
ROOT-64

## Target Repos
- `~/dev/tccw-qitp-mcp-ml-predict` (NEW — MCP server)
- `~/dev/tccw-qitp-agents` (EXISTING — new agent handler + blueprint)

## Dependencies
P03 (simulation engine — training data source), P05 (market-data-mcp — feature inputs)

## Repo Structure (MCP)
```
tccw-qitp-mcp-ml-predict/
├── src/
│   └── qitp_mcp_ml_predict/
│       ├── __init__.py
│       ├── server.py              # MCP server entrypoint
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── predict.py         # predict() — run inference
│       │   ├── metadata.py        # get_model_metadata() — version, metrics, training date
│       │   └── explainability.py  # get_feature_importance() — SHAP values
│       ├── model/
│       │   ├── __init__.py
│       │   ├── loader.py          # Load model from S3 (qitp-model-artifacts)
│       │   ├── features.py        # Feature vector construction (7 features)
│       │   └── inference.py       # XGBoost predict + SHAP computation
│       ├── training/
│       │   ├── __init__.py
│       │   ├── pipeline.py        # Training pipeline: data→features→train→evaluate→store
│       │   ├── data_prep.py       # Historical gaps + outcomes → training dataset
│       │   └── sagemaker_job.py   # SageMaker Training Job launcher
│       ├── schemas.py             # PredictionRequest, PredictionResult, FeatureVector, ModelMetadata
│       └── composite_score.py     # Updated composite: gap(35%) + sentiment(25%) + technical(20%) + ml(20%)
├── tests/
│   ├── conftest.py
│   ├── test_predict.py
│   ├── test_features.py
│   ├── test_training.py
│   └── fixtures/
│       ├── sample_features.json
│       └── sample_model.joblib
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Repo Structure (Agent Handler)
```
tccw-qitp-agents/
├── blueprints/
│   └── agents/
│       └── ml_predictor.yaml
├── src/
│   └── qitp_agents/
│       └── ml_predictor/
│           ├── __init__.py
│           └── handler.py
```

## MCP Tools (3 total)

| Tool | Input | Output |
|---|---|---|
| `predict` | symbol, features dict, horizons | direction (UP/DOWN/NEUTRAL), confidence, predictions at T+1/T+3/T+5 |
| `get_model_metadata` | model_id (optional) | version, training_date, accuracy, AUC, brier_score, feature_list |
| `get_feature_importance` | symbol, features dict | SHAP values per feature, ranked by importance |

## Feature Vector (7 features)

| # | Name | Description | Source |
|---|---|---|---|
| 1 | `gap_pct` | Gap percentage (Friday close to Monday open) | market-data-mcp |
| 2 | `volume_ratio` | Monday open volume / 20-day avg volume | market-data-mcp |
| 3 | `sentiment_score` | Composite sentiment (-1.0 to 1.0) | sentiment-mcp |
| 4 | `vix_level` | VIX at time of gap | market-data-mcp |
| 5 | `sector_encoded` | Label-encoded sector (0-10) | watchlist config |
| 6 | `prior_week_return` | Return over prior 5 trading days | market-data-mcp |
| 7 | `analyst_revision` | Net analyst revisions (upgrades - downgrades) | sentiment-mcp |

---

## Full Inline Code

---

### `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "qitp-mcp-ml-predict"
version = "0.1.0"
description = "QITP ML Prediction MCP Server — XGBoost price direction prediction with SHAP explainability"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",
    "pydantic>=2.0",
    "xgboost>=2.0",
    "shap>=0.44",
    "scikit-learn>=1.4",
    "numpy>=1.26",
    "pandas>=2.1",
    "boto3>=1.34",
    "joblib>=1.3",
    "uvicorn>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "moto[s3]>=5.0",
]
training = [
    "sagemaker>=2.200",
]

[project.scripts]
ml-predict-mcp = "qitp_mcp_ml_predict.server:main"

[tool.hatch.build.targets.wheel]
packages = ["src/qitp_mcp_ml_predict"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

---

### `src/qitp_mcp_ml_predict/__init__.py`

```python
"""QITP ML Prediction MCP Server."""

__version__ = "0.1.0"
```

---

### `src/qitp_mcp_ml_predict/schemas.py`

```python
"""Data schemas for ML prediction MCP server."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class FeatureVector(BaseModel):
    """7-feature input vector for XGBoost model."""

    gap_pct: float = Field(description="Gap percentage (Friday close -> Monday open)")
    volume_ratio: float = Field(description="Monday open volume / 20-day avg volume")
    sentiment_score: float = Field(description="Composite sentiment score (-1.0 to 1.0)")
    vix_level: float = Field(description="VIX level at time of gap")
    sector_encoded: int = Field(ge=0, le=10, description="Label-encoded sector (0-10)")
    prior_week_return: float = Field(description="Return over prior 5 trading days (%)")
    analyst_revision: float = Field(description="Net analyst revisions (upgrades - downgrades)")

    def to_array(self) -> list[float]:
        """Convert to ordered float array for model input."""
        return [
            self.gap_pct,
            self.volume_ratio,
            self.sentiment_score,
            self.vix_level,
            float(self.sector_encoded),
            self.prior_week_return,
            self.analyst_revision,
        ]

    @classmethod
    def feature_names(cls) -> list[str]:
        """Ordered feature names matching to_array() order."""
        return [
            "gap_pct",
            "volume_ratio",
            "sentiment_score",
            "vix_level",
            "sector_encoded",
            "prior_week_return",
            "analyst_revision",
        ]


class HorizonPrediction(BaseModel):
    """Prediction for a single time horizon."""

    horizon: str = Field(description="Time horizon label: T+1, T+3, or T+5")
    direction: Literal["UP", "DOWN", "NEUTRAL"] = Field(
        description="Predicted price direction"
    )
    probability_up: float = Field(ge=0.0, le=1.0, description="Probability of UP")
    probability_down: float = Field(ge=0.0, le=1.0, description="Probability of DOWN")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Model confidence (max probability)"
    )


class PredictionRequest(BaseModel):
    """Input for the predict tool."""

    symbol: str = Field(description="Ticker symbol")
    features: FeatureVector
    horizons: list[str] = Field(
        default=["T+1", "T+3", "T+5"],
        description="Time horizons to predict",
    )
    model_id: str = Field(
        default="gap_direction_xgb",
        description="Model identifier",
    )


class PredictionResult(BaseModel):
    """Output from the predict tool."""

    symbol: str
    model_id: str
    model_version: str
    predictions: list[HorizonPrediction]
    overall_direction: Literal["UP", "DOWN", "NEUTRAL"] = Field(
        description="Consensus direction across horizons"
    )
    overall_confidence: float = Field(
        ge=0.0, le=1.0, description="Average confidence across horizons"
    )
    ml_score: float = Field(
        description="Normalized ML score for composite formula (-1.0 to 1.0)"
    )
    prediction_timestamp: datetime


class FeatureImportance(BaseModel):
    """SHAP-based feature importance for a single prediction."""

    feature_name: str
    shap_value: float = Field(description="SHAP value (signed contribution)")
    abs_shap_value: float = Field(description="Absolute SHAP value for ranking")
    feature_value: float = Field(description="Actual feature value used")
    direction_contribution: Literal["bullish", "bearish", "neutral"] = Field(
        description="Whether this feature pushes toward UP or DOWN"
    )


class ExplainabilityResult(BaseModel):
    """Full SHAP explanation for a prediction."""

    symbol: str
    model_id: str
    model_version: str
    horizon: str
    base_value: float = Field(description="Expected value (base rate)")
    feature_importances: list[FeatureImportance] = Field(
        description="Features ranked by abs(SHAP value) descending"
    )
    prediction_value: float = Field(
        description="Final prediction value (base_value + sum of SHAP values)"
    )


class ModelMetrics(BaseModel):
    """Evaluation metrics from model training."""

    accuracy: float = Field(ge=0.0, le=1.0)
    auc_roc: float = Field(ge=0.0, le=1.0)
    brier_score: float = Field(ge=0.0, le=1.0, description="Lower is better")
    precision_up: float = Field(ge=0.0, le=1.0)
    recall_up: float = Field(ge=0.0, le=1.0)
    precision_down: float = Field(ge=0.0, le=1.0)
    recall_down: float = Field(ge=0.0, le=1.0)
    f1_macro: float = Field(ge=0.0, le=1.0)
    sample_count: int = Field(description="Number of training samples")


class ModelMetadata(BaseModel):
    """Metadata about a trained model."""

    model_id: str
    version: str
    training_date: date
    training_data_start: date
    training_data_end: date
    horizons: list[str]
    feature_names: list[str]
    metrics: ModelMetrics
    s3_path: str = Field(description="S3 path to model artifact")
    description: str = ""


class CompositeScoreInput(BaseModel):
    """Input for the updated composite score calculation."""

    gap_score: float = Field(description="Normalized gap score (0.0 to 1.0)")
    sentiment_score: float = Field(description="Normalized sentiment score (0.0 to 1.0)")
    technical_score: float = Field(description="Normalized technical score (0.0 to 1.0)")
    ml_score: float = Field(description="Normalized ML prediction score (0.0 to 1.0)")


class CompositeScoreResult(BaseModel):
    """Output of the updated composite score calculation."""

    composite_score: float = Field(
        description="Weighted composite (gap*0.35 + sentiment*0.25 + technical*0.20 + ml*0.20)"
    )
    component_contributions: dict[str, float] = Field(
        description="Individual weighted contributions"
    )
    signal_strength: Literal["strong", "moderate", "weak"] = Field(
        description="Categorized signal strength"
    )
```

---

### `src/qitp_mcp_ml_predict/model/__init__.py`

```python
"""Model loading, feature engineering, and inference."""
```

---

### `src/qitp_mcp_ml_predict/model/loader.py`

```python
"""Load XGBoost models from S3 model artifact store.

Model layout in S3:
    s3://qitp-model-artifacts/{model_id}/v{version}/model.joblib
    s3://qitp-model-artifacts/{model_id}/v{version}/metadata.json
    s3://qitp-model-artifacts/{model_id}/latest  (contains version string)
"""

from __future__ import annotations

import io
import json
import logging
import os
import tempfile
from typing import Any

import boto3
import joblib

logger = logging.getLogger(__name__)

_model_cache: dict[str, dict[str, Any]] = {}


def _get_s3_client():
    """Get boto3 S3 client."""
    return boto3.client("s3")


def _override_s3_client(client):
    """Override S3 client for testing."""
    global _s3_override
    _s3_override = client


_s3_override = None


def _s3():
    """Return S3 client (test-overridable)."""
    if _s3_override is not None:
        return _s3_override
    return _get_s3_client()


def _bucket() -> str:
    """Model artifacts S3 bucket."""
    return os.environ.get("S3_MODEL_ARTIFACTS_BUCKET", "qitp-model-artifacts")


def get_latest_version(model_id: str) -> str:
    """Fetch the latest version string for a model.

    Reads s3://{bucket}/{model_id}/latest which contains the version string.
    """
    try:
        resp = _s3().get_object(
            Bucket=_bucket(),
            Key=f"{model_id}/latest",
        )
        version = resp["Body"].read().decode("utf-8").strip()
        logger.info("Latest version for %s: %s", model_id, version)
        return version
    except Exception:
        logger.warning("Could not fetch latest version for %s, defaulting to v1", model_id)
        return "v1"


def load_model(model_id: str, version: str | None = None) -> Any:
    """Load an XGBoost model from S3.

    Uses an in-memory cache to avoid reloading on warm Lambda invocations.

    Args:
        model_id: Model identifier (e.g. "gap_direction_xgb").
        version: Specific version (e.g. "v1"). If None, loads latest.

    Returns:
        The deserialized XGBoost model object.
    """
    if version is None:
        version = get_latest_version(model_id)

    cache_key = f"{model_id}/{version}"
    if cache_key in _model_cache:
        logger.debug("Model cache hit: %s", cache_key)
        return _model_cache[cache_key]["model"]

    s3_key = f"{model_id}/{version}/model.joblib"
    logger.info("Loading model from s3://%s/%s", _bucket(), s3_key)

    try:
        resp = _s3().get_object(Bucket=_bucket(), Key=s3_key)
        body = resp["Body"].read()

        # joblib needs a file-like object or temp file
        with tempfile.NamedTemporaryFile(suffix=".joblib", delete=True) as tmp:
            tmp.write(body)
            tmp.flush()
            tmp.seek(0)
            model = joblib.load(tmp.name)

        _model_cache[cache_key] = {"model": model, "version": version}
        logger.info("Model loaded and cached: %s", cache_key)
        return model

    except Exception:
        logger.exception("Failed to load model from s3://%s/%s", _bucket(), s3_key)
        raise


def load_metadata(model_id: str, version: str | None = None) -> dict[str, Any]:
    """Load model metadata JSON from S3.

    Args:
        model_id: Model identifier.
        version: Specific version. If None, loads latest.

    Returns:
        Metadata dictionary.
    """
    if version is None:
        version = get_latest_version(model_id)

    cache_key = f"{model_id}/{version}"
    if cache_key in _model_cache and "metadata" in _model_cache[cache_key]:
        return _model_cache[cache_key]["metadata"]

    s3_key = f"{model_id}/{version}/metadata.json"
    logger.info("Loading metadata from s3://%s/%s", _bucket(), s3_key)

    try:
        resp = _s3().get_object(Bucket=_bucket(), Key=s3_key)
        metadata = json.loads(resp["Body"].read().decode("utf-8"))

        if cache_key not in _model_cache:
            _model_cache[cache_key] = {}
        _model_cache[cache_key]["metadata"] = metadata

        return metadata

    except Exception:
        logger.exception("Failed to load metadata from s3://%s/%s", _bucket(), s3_key)
        raise


def clear_cache() -> None:
    """Clear the model cache (useful for testing and forced reload)."""
    _model_cache.clear()
    logger.info("Model cache cleared")


def store_model(
    model: Any,
    metadata: dict[str, Any],
    model_id: str,
    version: str,
) -> str:
    """Store a trained model and metadata to S3.

    Args:
        model: Trained XGBoost model.
        metadata: Metadata dictionary.
        model_id: Model identifier.
        version: Version string (e.g. "v2").

    Returns:
        S3 path prefix where model was stored.
    """
    bucket = _bucket()
    prefix = f"{model_id}/{version}"

    # Store model
    with tempfile.NamedTemporaryFile(suffix=".joblib", delete=True) as tmp:
        joblib.dump(model, tmp.name)
        tmp.seek(0)
        model_bytes = open(tmp.name, "rb").read()

    _s3().put_object(
        Bucket=bucket,
        Key=f"{prefix}/model.joblib",
        Body=model_bytes,
    )

    # Store metadata
    _s3().put_object(
        Bucket=bucket,
        Key=f"{prefix}/metadata.json",
        Body=json.dumps(metadata, default=str).encode("utf-8"),
    )

    # Update latest pointer
    _s3().put_object(
        Bucket=bucket,
        Key=f"{model_id}/latest",
        Body=version.encode("utf-8"),
    )

    logger.info("Model stored at s3://%s/%s/", bucket, prefix)
    return f"s3://{bucket}/{prefix}/"
```

---

### `src/qitp_mcp_ml_predict/model/features.py`

```python
"""Feature vector construction for ML prediction.

The 7-feature vector:
    1. gap_pct           — Gap percentage (Friday close -> Monday open)
    2. volume_ratio      — Monday open volume / 20-day avg volume
    3. sentiment_score   — Composite sentiment (-1.0 to 1.0)
    4. vix_level         — VIX at time of gap
    5. sector_encoded    — Label-encoded sector (0-10)
    6. prior_week_return — Return over prior 5 trading days (%)
    7. analyst_revision  — Net analyst revisions (upgrades - downgrades)
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from qitp_mcp_ml_predict.schemas import FeatureVector

logger = logging.getLogger(__name__)

# Sector label encoding — deterministic mapping
SECTOR_ENCODING: dict[str, int] = {
    "Technology": 0,
    "Healthcare": 1,
    "Financials": 2,
    "Consumer Discretionary": 3,
    "Consumer Staples": 4,
    "Energy": 5,
    "Industrials": 6,
    "Materials": 7,
    "Utilities": 8,
    "Real Estate": 9,
    "Communication Services": 10,
}

# Default sector for unknowns
DEFAULT_SECTOR_CODE = 0


def encode_sector(sector: str) -> int:
    """Encode a sector string to its integer label.

    Args:
        sector: Sector name (e.g. "Technology").

    Returns:
        Integer label (0-10).
    """
    return SECTOR_ENCODING.get(sector, DEFAULT_SECTOR_CODE)


def build_feature_vector(
    gap_pct: float,
    volume_ratio: float,
    sentiment_score: float,
    vix_level: float,
    sector: str | int,
    prior_week_return: float,
    analyst_revision: float,
) -> FeatureVector:
    """Build a validated FeatureVector from raw inputs.

    Args:
        gap_pct: Gap percentage.
        volume_ratio: Volume ratio.
        sentiment_score: Composite sentiment (-1.0 to 1.0).
        vix_level: VIX level.
        sector: Sector name (str) or pre-encoded integer.
        prior_week_return: Prior week return (%).
        analyst_revision: Net analyst revisions.

    Returns:
        Validated FeatureVector.
    """
    sector_code = sector if isinstance(sector, int) else encode_sector(sector)

    return FeatureVector(
        gap_pct=gap_pct,
        volume_ratio=volume_ratio,
        sentiment_score=max(-1.0, min(1.0, sentiment_score)),
        vix_level=max(0.0, vix_level),
        sector_encoded=max(0, min(10, sector_code)),
        prior_week_return=prior_week_return,
        analyst_revision=analyst_revision,
    )


def build_feature_vector_from_dict(data: dict[str, Any]) -> FeatureVector:
    """Build a FeatureVector from a flat dictionary.

    Handles both pre-encoded sector_encoded and raw sector name.

    Args:
        data: Dictionary with feature values.

    Returns:
        Validated FeatureVector.
    """
    sector = data.get("sector_encoded", data.get("sector", 0))

    return build_feature_vector(
        gap_pct=float(data.get("gap_pct", 0.0)),
        volume_ratio=float(data.get("volume_ratio", 1.0)),
        sentiment_score=float(data.get("sentiment_score", 0.0)),
        vix_level=float(data.get("vix_level", 20.0)),
        sector=sector,
        prior_week_return=float(data.get("prior_week_return", 0.0)),
        analyst_revision=float(data.get("analyst_revision", 0.0)),
    )


def features_to_numpy(features: FeatureVector) -> np.ndarray:
    """Convert a FeatureVector to a numpy array shaped (1, 7) for model input.

    Args:
        features: Validated FeatureVector.

    Returns:
        numpy array of shape (1, 7).
    """
    return np.array([features.to_array()], dtype=np.float64)


def validate_feature_ranges(features: FeatureVector) -> list[str]:
    """Check feature values for suspicious ranges and return warnings.

    Does NOT reject — just warns. Useful for logging anomalies.

    Args:
        features: FeatureVector to validate.

    Returns:
        List of warning strings (empty if all looks normal).
    """
    warnings: list[str] = []

    if abs(features.gap_pct) > 20.0:
        warnings.append(f"gap_pct={features.gap_pct} is unusually large (>20%)")

    if features.volume_ratio > 10.0:
        warnings.append(f"volume_ratio={features.volume_ratio} is unusually high (>10x)")

    if features.vix_level > 80.0:
        warnings.append(f"vix_level={features.vix_level} is extreme (>80)")

    if abs(features.prior_week_return) > 30.0:
        warnings.append(
            f"prior_week_return={features.prior_week_return} is unusually large (>30%)"
        )

    if abs(features.analyst_revision) > 50:
        warnings.append(
            f"analyst_revision={features.analyst_revision} is unusually large (>50)"
        )

    return warnings
```

---

### `src/qitp_mcp_ml_predict/model/inference.py`

```python
"""XGBoost inference and SHAP computation.

Handles prediction for three horizons (T+1, T+3, T+5) using separate
models or a single multi-output model. Computes SHAP values for
explainability.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np
import shap

from qitp_mcp_ml_predict.model.features import features_to_numpy, validate_feature_ranges
from qitp_mcp_ml_predict.model.loader import load_metadata, load_model
from qitp_mcp_ml_predict.schemas import (
    ExplainabilityResult,
    FeatureImportance,
    FeatureVector,
    HorizonPrediction,
    PredictionResult,
)

logger = logging.getLogger(__name__)

# Direction thresholds: probability must exceed this to be called UP or DOWN
DIRECTION_THRESHOLD = 0.55
NEUTRAL_BAND = 0.45  # Below this on both sides = NEUTRAL


def _classify_direction(prob_up: float) -> str:
    """Classify direction from UP probability.

    Args:
        prob_up: Probability of UP direction (0.0 to 1.0).

    Returns:
        "UP", "DOWN", or "NEUTRAL".
    """
    if prob_up >= DIRECTION_THRESHOLD:
        return "UP"
    elif prob_up <= (1.0 - DIRECTION_THRESHOLD):
        return "DOWN"
    else:
        return "NEUTRAL"


def _compute_ml_score(predictions: list[HorizonPrediction]) -> float:
    """Compute normalized ML score from horizon predictions.

    Returns a value between -1.0 and 1.0:
    - Positive = bullish consensus
    - Negative = bearish consensus
    - Near zero = mixed/neutral

    Formula: weighted average of (prob_up - 0.5) * 2 across horizons,
    with T+1 weighted highest.
    """
    if not predictions:
        return 0.0

    # Horizon weights: T+1 gets most weight (nearest, most actionable)
    horizon_weights = {"T+1": 0.5, "T+3": 0.3, "T+5": 0.2}
    total_weight = 0.0
    weighted_sum = 0.0

    for pred in predictions:
        weight = horizon_weights.get(pred.horizon, 0.2)
        # Map prob_up from [0, 1] to [-1, 1]
        directional_signal = (pred.probability_up - 0.5) * 2.0
        weighted_sum += directional_signal * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    return max(-1.0, min(1.0, weighted_sum / total_weight))


def predict(
    symbol: str,
    features: FeatureVector,
    horizons: list[str] | None = None,
    model_id: str = "gap_direction_xgb",
) -> PredictionResult:
    """Run XGBoost inference for one or more time horizons.

    Each horizon has its own model variant stored under:
        {model_id}_t1, {model_id}_t3, {model_id}_t5

    If a unified model is used (single model_id), it returns predictions
    for all horizons from one model.

    Args:
        symbol: Ticker symbol.
        features: Validated feature vector.
        horizons: List of horizons (default: ["T+1", "T+3", "T+5"]).
        model_id: Base model identifier.

    Returns:
        PredictionResult with per-horizon predictions and overall direction.
    """
    if horizons is None:
        horizons = ["T+1", "T+3", "T+5"]

    # Validate features and log warnings
    warnings = validate_feature_ranges(features)
    for w in warnings:
        logger.warning("Feature range warning for %s: %s", symbol, w)

    X = features_to_numpy(features)
    horizon_predictions: list[HorizonPrediction] = []
    model_version = "unknown"

    # Map horizon labels to model suffixes
    horizon_suffix_map = {"T+1": "t1", "T+3": "t3", "T+5": "t5"}

    for horizon in horizons:
        suffix = horizon_suffix_map.get(horizon, horizon.lower().replace("+", ""))
        variant_id = f"{model_id}_{suffix}"

        try:
            model = load_model(variant_id)
            metadata = load_metadata(variant_id)
            model_version = metadata.get("version", "v1")
        except Exception:
            # Fall back to base model if horizon-specific variant doesn't exist
            logger.info("No variant %s found, falling back to base model %s", variant_id, model_id)
            model = load_model(model_id)
            metadata = load_metadata(model_id)
            model_version = metadata.get("version", "v1")

        # XGBoost predict_proba returns [[prob_class_0, prob_class_1]]
        # Class 1 = UP, Class 0 = DOWN
        proba = model.predict_proba(X)
        prob_up = float(proba[0][1])
        prob_down = float(proba[0][0])
        direction = _classify_direction(prob_up)
        confidence = max(prob_up, prob_down)

        horizon_predictions.append(
            HorizonPrediction(
                horizon=horizon,
                direction=direction,
                probability_up=round(prob_up, 4),
                probability_down=round(prob_down, 4),
                confidence=round(confidence, 4),
            )
        )

    # Overall direction: majority vote weighted by confidence
    direction_votes = {"UP": 0.0, "DOWN": 0.0, "NEUTRAL": 0.0}
    for pred in horizon_predictions:
        direction_votes[pred.direction] += pred.confidence

    overall_direction = max(direction_votes, key=direction_votes.get)
    overall_confidence = round(
        sum(p.confidence for p in horizon_predictions) / len(horizon_predictions), 4
    )

    ml_score = _compute_ml_score(horizon_predictions)

    return PredictionResult(
        symbol=symbol,
        model_id=model_id,
        model_version=model_version,
        predictions=horizon_predictions,
        overall_direction=overall_direction,
        overall_confidence=overall_confidence,
        ml_score=round(ml_score, 4),
        prediction_timestamp=datetime.now(timezone.utc),
    )


def compute_shap_values(
    features: FeatureVector,
    model_id: str = "gap_direction_xgb",
    horizon: str = "T+1",
) -> ExplainabilityResult:
    """Compute SHAP values for a prediction using TreeExplainer.

    Args:
        features: Validated feature vector.
        model_id: Base model identifier.
        horizon: Which horizon model to explain.

    Returns:
        ExplainabilityResult with ranked feature importances.
    """
    suffix = horizon.lower().replace("+", "").replace("t", "t")
    variant_id = f"{model_id}_{suffix}"

    try:
        model = load_model(variant_id)
        metadata = load_metadata(variant_id)
    except Exception:
        model = load_model(model_id)
        metadata = load_metadata(model_id)

    X = features_to_numpy(features)
    feature_names = FeatureVector.feature_names()
    feature_values = features.to_array()

    # SHAP TreeExplainer for XGBoost
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)

    # For binary classification, shap_values may be a list of two arrays
    # (one per class). We use class 1 (UP) SHAP values.
    if isinstance(shap_values, list):
        sv = shap_values[1][0]  # Class 1 (UP), first sample
    else:
        sv = shap_values[0]  # Single output

    base_value = float(explainer.expected_value)
    if isinstance(explainer.expected_value, (list, np.ndarray)):
        base_value = float(explainer.expected_value[1])  # Class 1 base value

    importances: list[FeatureImportance] = []
    for i, fname in enumerate(feature_names):
        shap_val = float(sv[i])
        importances.append(
            FeatureImportance(
                feature_name=fname,
                shap_value=round(shap_val, 6),
                abs_shap_value=round(abs(shap_val), 6),
                feature_value=round(feature_values[i], 6),
                direction_contribution=(
                    "bullish" if shap_val > 0.01 else "bearish" if shap_val < -0.01 else "neutral"
                ),
            )
        )

    # Sort by absolute SHAP value descending
    importances.sort(key=lambda x: x.abs_shap_value, reverse=True)

    prediction_value = base_value + sum(float(sv[i]) for i in range(len(sv)))

    return ExplainabilityResult(
        symbol="",  # Caller sets this
        model_id=model_id,
        model_version=metadata.get("version", "v1"),
        horizon=horizon,
        base_value=round(base_value, 6),
        feature_importances=importances,
        prediction_value=round(prediction_value, 6),
    )
```

---

### `src/qitp_mcp_ml_predict/composite_score.py`

```python
"""Updated composite score formula including ML prediction weight.

Previous formula: gap(40%) + sentiment(30%) + technical(30%)
Updated formula:  gap(35%) + sentiment(25%) + technical(20%) + ml(20%)

This module provides the canonical composite score computation used by
the Portfolio Recommender agent to rank symbols.
"""

from __future__ import annotations

from qitp_mcp_ml_predict.schemas import CompositeScoreInput, CompositeScoreResult

# Weight configuration — easily tunable
WEIGHTS = {
    "gap": 0.35,
    "sentiment": 0.25,
    "technical": 0.20,
    "ml": 0.20,
}

# Signal strength thresholds
STRONG_THRESHOLD = 0.70
MODERATE_THRESHOLD = 0.40


def compute_composite_score(inputs: CompositeScoreInput) -> CompositeScoreResult:
    """Compute the weighted composite score.

    All input scores should be normalized to [0.0, 1.0] before calling.

    Args:
        inputs: Normalized component scores.

    Returns:
        CompositeScoreResult with weighted composite and signal strength.
    """
    gap_contribution = inputs.gap_score * WEIGHTS["gap"]
    sentiment_contribution = inputs.sentiment_score * WEIGHTS["sentiment"]
    technical_contribution = inputs.technical_score * WEIGHTS["technical"]
    ml_contribution = inputs.ml_score * WEIGHTS["ml"]

    composite = gap_contribution + sentiment_contribution + technical_contribution + ml_contribution

    # Clamp to [0, 1]
    composite = max(0.0, min(1.0, composite))

    # Classify signal strength
    if composite >= STRONG_THRESHOLD:
        strength = "strong"
    elif composite >= MODERATE_THRESHOLD:
        strength = "moderate"
    else:
        strength = "weak"

    return CompositeScoreResult(
        composite_score=round(composite, 4),
        component_contributions={
            "gap": round(gap_contribution, 4),
            "sentiment": round(sentiment_contribution, 4),
            "technical": round(technical_contribution, 4),
            "ml": round(ml_contribution, 4),
        },
        signal_strength=strength,
    )


def normalize_ml_score_to_unit(ml_score: float) -> float:
    """Convert ML score from [-1.0, 1.0] range to [0.0, 1.0] for composite input.

    The ml_score from PredictionResult is in [-1, 1] (bearish to bullish).
    The composite formula expects [0, 1].

    Args:
        ml_score: ML score in [-1.0, 1.0].

    Returns:
        Normalized score in [0.0, 1.0].
    """
    return max(0.0, min(1.0, (ml_score + 1.0) / 2.0))
```

---

### `src/qitp_mcp_ml_predict/training/__init__.py`

```python
"""Training pipeline for ML prediction models."""
```

---

### `src/qitp_mcp_ml_predict/training/data_prep.py`

```python
"""Data preparation for ML model training.

Converts historical gap data + outcomes into labeled training datasets.
Labels: UP (price higher at T+N) or DOWN (price lower at T+N).

Data source: S3 parquet files with historical OHLCV data.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Minimum gap abs percentage to include in training data
MIN_GAP_PCT_FOR_TRAINING = 0.5


def compute_outcome(
    monday_open: float,
    future_close: float,
) -> int:
    """Compute binary outcome: 1 = UP (future_close > monday_open), 0 = DOWN.

    Args:
        monday_open: Monday opening price.
        future_close: Closing price at T+N.

    Returns:
        1 if UP, 0 if DOWN.
    """
    return 1 if future_close > monday_open else 0


def build_training_record(
    symbol: str,
    monday_date: date,
    gap_pct: float,
    volume_ratio: float,
    sentiment_score: float,
    vix_level: float,
    sector_encoded: int,
    prior_week_return: float,
    analyst_revision: float,
    outcome_t1: int,
    outcome_t3: int,
    outcome_t5: int,
) -> dict[str, Any]:
    """Build a single training record with features and labels.

    Args:
        symbol: Ticker symbol.
        monday_date: Date of the gap.
        Features 1-7 as named.
        outcome_t1/t3/t5: Binary outcome labels.

    Returns:
        Dictionary with all fields.
    """
    return {
        "symbol": symbol,
        "date": monday_date,
        "gap_pct": gap_pct,
        "volume_ratio": volume_ratio,
        "sentiment_score": sentiment_score,
        "vix_level": vix_level,
        "sector_encoded": sector_encoded,
        "prior_week_return": prior_week_return,
        "analyst_revision": analyst_revision,
        "outcome_t1": outcome_t1,
        "outcome_t3": outcome_t3,
        "outcome_t5": outcome_t5,
    }


def prepare_training_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert training records to a pandas DataFrame with proper types.

    Args:
        records: List of training record dicts.

    Returns:
        DataFrame ready for XGBoost training.
    """
    df = pd.DataFrame(records)

    if df.empty:
        logger.warning("Empty training dataset")
        return df

    # Ensure numeric types
    feature_cols = [
        "gap_pct", "volume_ratio", "sentiment_score",
        "vix_level", "sector_encoded", "prior_week_return", "analyst_revision",
    ]
    for col in feature_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    label_cols = ["outcome_t1", "outcome_t3", "outcome_t5"]
    for col in label_cols:
        df[col] = df[col].astype(int)

    # Drop rows with NaN features
    initial_count = len(df)
    df = df.dropna(subset=feature_cols)
    dropped = initial_count - len(df)
    if dropped > 0:
        logger.warning("Dropped %d rows with NaN features", dropped)

    # Filter out very small gaps (noise)
    df = df[df["gap_pct"].abs() >= MIN_GAP_PCT_FOR_TRAINING]

    logger.info(
        "Training dataset: %d records, %d UP at T+1, %d DOWN at T+1",
        len(df),
        (df["outcome_t1"] == 1).sum(),
        (df["outcome_t1"] == 0).sum(),
    )

    return df.reset_index(drop=True)


def split_features_labels(
    df: pd.DataFrame,
    horizon: str = "t1",
) -> tuple[np.ndarray, np.ndarray]:
    """Split DataFrame into feature matrix X and label vector y.

    Args:
        df: Training DataFrame from prepare_training_dataframe().
        horizon: Which outcome to use as label ("t1", "t3", "t5").

    Returns:
        Tuple of (X, y) as numpy arrays.
    """
    feature_cols = [
        "gap_pct", "volume_ratio", "sentiment_score",
        "vix_level", "sector_encoded", "prior_week_return", "analyst_revision",
    ]
    label_col = f"outcome_{horizon}"

    if label_col not in df.columns:
        raise ValueError(f"Label column {label_col} not found in DataFrame")

    X = df[feature_cols].values.astype(np.float64)
    y = df[label_col].values.astype(int)

    return X, y
```

---

### `src/qitp_mcp_ml_predict/training/pipeline.py`

```python
"""Training pipeline: data preparation -> feature engineering -> training -> evaluation -> storage.

This runs locally or on SageMaker. The pipeline:
1. Load historical gap data from training records
2. Build feature matrices and label vectors
3. Train XGBoost classifiers (one per horizon)
4. Evaluate: accuracy, AUC-ROC, Brier score, precision/recall
5. Store model + metadata to S3
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from qitp_mcp_ml_predict.model.loader import store_model
from qitp_mcp_ml_predict.schemas import ModelMetadata, ModelMetrics
from qitp_mcp_ml_predict.training.data_prep import (
    prepare_training_dataframe,
    split_features_labels,
)

logger = logging.getLogger(__name__)

# XGBoost hyperparameters (tuned for gap trading classification)
DEFAULT_PARAMS = {
    "n_estimators": 200,
    "max_depth": 5,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 3,
    "gamma": 0.1,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "scale_pos_weight": 1.0,  # Adjusted per-dataset if imbalanced
    "eval_metric": "logloss",
    "random_state": 42,
    "use_label_encoder": False,
}


def _evaluate_model(
    model: XGBClassifier,
    X_test: np.ndarray,
    y_test: np.ndarray,
) -> ModelMetrics:
    """Evaluate a trained model on test data.

    Args:
        model: Trained XGBClassifier.
        X_test: Test feature matrix.
        y_test: Test labels.

    Returns:
        ModelMetrics with all evaluation metrics.
    """
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    accuracy = accuracy_score(y_test, y_pred)
    auc_roc = roc_auc_score(y_test, y_proba)
    brier = brier_score_loss(y_test, y_proba)
    precision_up = precision_score(y_test, y_pred, pos_label=1, zero_division=0)
    recall_up = recall_score(y_test, y_pred, pos_label=1, zero_division=0)
    precision_down = precision_score(y_test, y_pred, pos_label=0, zero_division=0)
    recall_down = recall_score(y_test, y_pred, pos_label=0, zero_division=0)
    f1 = f1_score(y_test, y_pred, average="macro", zero_division=0)

    return ModelMetrics(
        accuracy=round(accuracy, 4),
        auc_roc=round(auc_roc, 4),
        brier_score=round(brier, 4),
        precision_up=round(precision_up, 4),
        recall_up=round(recall_up, 4),
        precision_down=round(precision_down, 4),
        recall_down=round(recall_down, 4),
        f1_macro=round(f1, 4),
        sample_count=len(y_test),
    )


def train_horizon_model(
    records: list[dict[str, Any]],
    horizon: str,
    model_id: str,
    version: str,
    params: dict[str, Any] | None = None,
    test_size: float = 0.2,
) -> tuple[XGBClassifier, ModelMetrics, str]:
    """Train an XGBoost model for a specific horizon.

    Args:
        records: Training records from data_prep.
        horizon: "t1", "t3", or "t5".
        model_id: Base model identifier.
        version: Version string.
        params: XGBoost parameters (defaults to DEFAULT_PARAMS).
        test_size: Fraction of data for test split.

    Returns:
        Tuple of (trained_model, metrics, s3_path).
    """
    if params is None:
        params = DEFAULT_PARAMS.copy()

    df = prepare_training_dataframe(records)
    if len(df) < 50:
        raise ValueError(
            f"Insufficient training data: {len(df)} records (minimum 50 required)"
        )

    X, y = split_features_labels(df, horizon)

    # Handle class imbalance
    n_pos = y.sum()
    n_neg = len(y) - n_pos
    if n_neg > 0 and n_pos > 0:
        params["scale_pos_weight"] = n_neg / n_pos

    # Train/test split with stratification
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=y
    )

    logger.info(
        "Training %s_%s: %d train, %d test, %.1f%% UP rate",
        model_id, horizon, len(X_train), len(X_test),
        100 * y_train.mean(),
    )

    # Train XGBoost
    model = XGBClassifier(**params)
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    # Evaluate
    metrics = _evaluate_model(model, X_test, y_test)
    logger.info(
        "Model %s_%s metrics: accuracy=%.3f, AUC=%.3f, Brier=%.3f",
        model_id, horizon, metrics.accuracy, metrics.auc_roc, metrics.brier_score,
    )

    # Determine date range from records
    dates = [r["date"] for r in records if isinstance(r.get("date"), date)]
    data_start = min(dates) if dates else date.today()
    data_end = max(dates) if dates else date.today()

    # Build metadata
    from qitp_mcp_ml_predict.schemas import FeatureVector

    metadata_dict = ModelMetadata(
        model_id=f"{model_id}_{horizon}",
        version=version,
        training_date=date.today(),
        training_data_start=data_start,
        training_data_end=data_end,
        horizons=[horizon],
        feature_names=FeatureVector.feature_names(),
        metrics=metrics,
        s3_path=f"s3://qitp-model-artifacts/{model_id}_{horizon}/{version}/",
        description=f"XGBoost gap direction classifier for {horizon} horizon",
    ).model_dump(mode="json")

    # Store to S3
    variant_id = f"{model_id}_{horizon}"
    s3_path = store_model(model, metadata_dict, variant_id, version)

    return model, metrics, s3_path


def run_full_pipeline(
    records: list[dict[str, Any]],
    model_id: str = "gap_direction_xgb",
    version: str = "v1",
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the full training pipeline for all three horizons.

    Args:
        records: Training records.
        model_id: Base model identifier.
        version: Version string.
        params: XGBoost parameters.

    Returns:
        Summary dict with per-horizon metrics and S3 paths.
    """
    results: dict[str, Any] = {
        "model_id": model_id,
        "version": version,
        "training_date": datetime.now(timezone.utc).isoformat(),
        "horizons": {},
    }

    for horizon in ["t1", "t3", "t5"]:
        try:
            _, metrics, s3_path = train_horizon_model(
                records, horizon, model_id, version, params
            )
            results["horizons"][horizon] = {
                "metrics": metrics.model_dump(),
                "s3_path": s3_path,
                "status": "success",
            }
        except Exception as e:
            logger.exception("Failed to train %s_%s", model_id, horizon)
            results["horizons"][horizon] = {
                "status": "failed",
                "error": str(e),
            }

    # Overall success if at least T+1 succeeded
    results["overall_status"] = (
        "success" if results["horizons"].get("t1", {}).get("status") == "success"
        else "failed"
    )

    return results
```

---

### `src/qitp_mcp_ml_predict/training/sagemaker_job.py`

```python
"""SageMaker Training Job launcher for production-scale model training.

In Phase 2, training migrates from local to SageMaker for:
- GPU-accelerated training on larger datasets
- Managed hyperparameter tuning
- Model registry integration
- Automatic model deployment

For POC (Phase 1), training runs locally via pipeline.py.
This module provides the SageMaker integration for Phase 2 graduation.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3

logger = logging.getLogger(__name__)


def _sagemaker_client():
    """Get SageMaker client."""
    region = os.environ.get("SAGEMAKER_REGION", "us-west-2")
    return boto3.client("sagemaker", region_name=region)


def launch_training_job(
    model_id: str,
    version: str,
    training_data_s3: str,
    instance_type: str = "ml.m5.xlarge",
    hyperparameters: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Launch a SageMaker training job for the XGBoost model.

    Args:
        model_id: Model identifier.
        version: Version string.
        training_data_s3: S3 URI of training data (CSV or parquet).
        instance_type: SageMaker instance type.
        hyperparameters: XGBoost hyperparameters as strings.

    Returns:
        Dict with job name, ARN, and status.
    """
    if hyperparameters is None:
        hyperparameters = {
            "max_depth": "5",
            "eta": "0.05",
            "subsample": "0.8",
            "colsample_bytree": "0.8",
            "num_round": "200",
            "objective": "binary:logistic",
            "eval_metric": "logloss",
        }

    job_name = f"qitp-{model_id}-{version}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    role_arn = os.environ.get("SAGEMAKER_ROLE_ARN", "")
    output_bucket = os.environ.get("S3_MODEL_ARTIFACTS_BUCKET", "qitp-model-artifacts")

    if not role_arn:
        raise ValueError("SAGEMAKER_ROLE_ARN env var must be set for SageMaker training")

    region = os.environ.get("SAGEMAKER_REGION", "us-west-2")
    image_uri = f"683313688378.dkr.ecr.{region}.amazonaws.com/sagemaker-xgboost:1.7-1"

    training_params = {
        "TrainingJobName": job_name,
        "AlgorithmSpecification": {
            "TrainingImage": image_uri,
            "TrainingInputMode": "File",
        },
        "RoleArn": role_arn,
        "InputDataConfig": [
            {
                "ChannelName": "train",
                "DataSource": {
                    "S3DataSource": {
                        "S3DataType": "S3Prefix",
                        "S3Uri": training_data_s3,
                        "S3DataDistributionType": "FullyReplicated",
                    }
                },
                "ContentType": "text/csv",
            }
        ],
        "OutputDataConfig": {
            "S3OutputPath": f"s3://{output_bucket}/{model_id}/{version}/sagemaker-output/",
        },
        "ResourceConfig": {
            "InstanceType": instance_type,
            "InstanceCount": 1,
            "VolumeSizeInGB": 10,
        },
        "StoppingCondition": {
            "MaxRuntimeInSeconds": 3600,
        },
        "HyperParameters": hyperparameters,
        "Tags": [
            {"Key": "project", "Value": "qitp"},
            {"Key": "model_id", "Value": model_id},
            {"Key": "version", "Value": version},
        ],
    }

    client = _sagemaker_client()
    response = client.create_training_job(**training_params)

    logger.info("SageMaker training job launched: %s", job_name)

    return {
        "job_name": job_name,
        "job_arn": response.get("TrainingJobArn", ""),
        "status": "InProgress",
        "output_path": f"s3://{output_bucket}/{model_id}/{version}/sagemaker-output/",
    }


def get_training_job_status(job_name: str) -> dict[str, Any]:
    """Get the status of a SageMaker training job.

    Args:
        job_name: Training job name.

    Returns:
        Dict with status, metrics, and output path.
    """
    client = _sagemaker_client()
    response = client.describe_training_job(TrainingJobName=job_name)

    status = response.get("TrainingJobStatus", "Unknown")
    metrics = {}

    if status == "Completed":
        for metric in response.get("FinalMetricDataList", []):
            metrics[metric["MetricName"]] = metric["Value"]

    return {
        "job_name": job_name,
        "status": status,
        "metrics": metrics,
        "output_path": response.get("OutputDataConfig", {}).get("S3OutputPath", ""),
        "failure_reason": response.get("FailureReason", ""),
    }
```

---

### `src/qitp_mcp_ml_predict/tools/__init__.py`

```python
"""MCP tool implementations for ML prediction server."""
```

---

### `src/qitp_mcp_ml_predict/tools/predict.py`

```python
"""predict tool — run XGBoost inference for a symbol."""

from __future__ import annotations

from typing import Any

from qitp_mcp_ml_predict.model.features import build_feature_vector_from_dict
from qitp_mcp_ml_predict.model.inference import predict as run_predict


async def predict(
    symbol: str,
    features: dict[str, Any],
    horizons: list[str] | None = None,
    model_id: str = "gap_direction_xgb",
) -> dict:
    """Predict price direction at T+1, T+3, T+5 horizons.

    Args:
        symbol: Ticker symbol (e.g. "AAPL").
        features: Dict with the 7 feature values:
            gap_pct, volume_ratio, sentiment_score, vix_level,
            sector_encoded (or sector), prior_week_return, analyst_revision.
        horizons: List of horizons to predict (default: ["T+1", "T+3", "T+5"]).
        model_id: Model identifier (default: "gap_direction_xgb").

    Returns:
        PredictionResult as dictionary with:
        - predictions: list of per-horizon results (direction, confidence, probabilities)
        - overall_direction: consensus direction
        - overall_confidence: average confidence
        - ml_score: normalized score for composite formula (-1.0 to 1.0)
    """
    feature_vector = build_feature_vector_from_dict(features)
    result = run_predict(symbol, feature_vector, horizons, model_id)
    return result.model_dump(mode="json")
```

---

### `src/qitp_mcp_ml_predict/tools/metadata.py`

```python
"""get_model_metadata tool — retrieve model version, metrics, and training info."""

from __future__ import annotations

from qitp_mcp_ml_predict.model.loader import get_latest_version, load_metadata
from qitp_mcp_ml_predict.schemas import ModelMetadata


async def get_model_metadata(
    model_id: str = "gap_direction_xgb",
    horizon: str | None = None,
) -> dict:
    """Get metadata about a trained model.

    Args:
        model_id: Base model identifier (default: "gap_direction_xgb").
        horizon: Specific horizon ("T+1", "T+3", "T+5"). If None, returns metadata
                 for the T+1 variant as the primary reference.

    Returns:
        ModelMetadata as dictionary with version, training_date, metrics, feature_names.
    """
    if horizon:
        suffix = horizon.lower().replace("+", "").replace("t", "t")
        variant_id = f"{model_id}_{suffix}"
    else:
        variant_id = f"{model_id}_t1"  # Default to T+1

    try:
        metadata = load_metadata(variant_id)
        return metadata
    except Exception:
        # Try base model if variant not found
        metadata = load_metadata(model_id)
        return metadata
```

---

### `src/qitp_mcp_ml_predict/tools/explainability.py`

```python
"""get_feature_importance tool — SHAP values for a specific prediction."""

from __future__ import annotations

from typing import Any

from qitp_mcp_ml_predict.model.features import build_feature_vector_from_dict
from qitp_mcp_ml_predict.model.inference import compute_shap_values


async def get_feature_importance(
    symbol: str,
    features: dict[str, Any],
    horizon: str = "T+1",
    model_id: str = "gap_direction_xgb",
    top_n: int | None = None,
) -> dict:
    """Get SHAP-based feature importance for a prediction.

    Args:
        symbol: Ticker symbol (for labeling).
        features: Dict with the 7 feature values.
        horizon: Which horizon to explain (default: "T+1").
        model_id: Model identifier.
        top_n: If set, return only the top N features by importance.

    Returns:
        ExplainabilityResult as dictionary with:
        - base_value: model baseline expectation
        - feature_importances: ranked list with SHAP values and contribution direction
        - prediction_value: base_value + sum(SHAP values)
    """
    feature_vector = build_feature_vector_from_dict(features)
    result = compute_shap_values(feature_vector, model_id, horizon)

    # Set the symbol (inference doesn't know it)
    result.symbol = symbol

    result_dict = result.model_dump(mode="json")

    # Truncate to top_n if requested
    if top_n is not None and top_n > 0:
        result_dict["feature_importances"] = result_dict["feature_importances"][:top_n]

    return result_dict
```

---

### `src/qitp_mcp_ml_predict/server.py`

```python
"""MCP server entrypoint — registers 3 tools and runs the server."""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("qitp_mcp_ml_predict")

# ---------------------------------------------------------------------------
# Build the MCP server
# ---------------------------------------------------------------------------

server = Server("ml-predict-mcp")


# ---------------------------------------------------------------------------
# Tool definitions (list_tools)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[Tool] = [
    Tool(
        name="predict",
        description=(
            "Predict price direction at T+1, T+3, T+5 horizons using XGBoost. "
            "Returns direction (UP/DOWN/NEUTRAL), confidence, probabilities, and "
            "a normalized ml_score for the composite score formula."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Ticker symbol (e.g. AAPL, TSLA)",
                },
                "features": {
                    "type": "object",
                    "description": "Feature vector with 7 fields",
                    "properties": {
                        "gap_pct": {"type": "number", "description": "Gap percentage"},
                        "volume_ratio": {"type": "number", "description": "Volume ratio"},
                        "sentiment_score": {"type": "number", "description": "Sentiment (-1 to 1)"},
                        "vix_level": {"type": "number", "description": "VIX level"},
                        "sector_encoded": {"type": "integer", "description": "Sector code (0-10)"},
                        "prior_week_return": {"type": "number", "description": "Prior week return %"},
                        "analyst_revision": {"type": "number", "description": "Net analyst revisions"},
                    },
                    "required": [
                        "gap_pct", "volume_ratio", "sentiment_score",
                        "vix_level", "sector_encoded", "prior_week_return", "analyst_revision",
                    ],
                },
                "horizons": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["T+1", "T+3", "T+5"]},
                    "default": ["T+1", "T+3", "T+5"],
                    "description": "Time horizons to predict",
                },
                "model_id": {
                    "type": "string",
                    "default": "gap_direction_xgb",
                    "description": "Model identifier",
                },
            },
            "required": ["symbol", "features"],
        },
    ),
    Tool(
        name="get_model_metadata",
        description=(
            "Get metadata about a trained ML model: version, training date, "
            "accuracy metrics (accuracy, AUC-ROC, Brier score), and feature list."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "model_id": {
                    "type": "string",
                    "default": "gap_direction_xgb",
                    "description": "Model identifier",
                },
                "horizon": {
                    "type": "string",
                    "enum": ["T+1", "T+3", "T+5"],
                    "description": "Specific horizon variant (optional, defaults to T+1)",
                },
            },
        },
    ),
    Tool(
        name="get_feature_importance",
        description=(
            "Get SHAP-based feature importance for a specific prediction. "
            "Returns ranked features with signed SHAP values showing each "
            "feature's contribution to the prediction (bullish/bearish)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Ticker symbol",
                },
                "features": {
                    "type": "object",
                    "description": "Feature vector with 7 fields (same as predict tool)",
                    "properties": {
                        "gap_pct": {"type": "number"},
                        "volume_ratio": {"type": "number"},
                        "sentiment_score": {"type": "number"},
                        "vix_level": {"type": "number"},
                        "sector_encoded": {"type": "integer"},
                        "prior_week_return": {"type": "number"},
                        "analyst_revision": {"type": "number"},
                    },
                    "required": [
                        "gap_pct", "volume_ratio", "sentiment_score",
                        "vix_level", "sector_encoded", "prior_week_return", "analyst_revision",
                    ],
                },
                "horizon": {
                    "type": "string",
                    "enum": ["T+1", "T+3", "T+5"],
                    "default": "T+1",
                    "description": "Which horizon to explain",
                },
                "model_id": {
                    "type": "string",
                    "default": "gap_direction_xgb",
                    "description": "Model identifier",
                },
                "top_n": {
                    "type": "integer",
                    "description": "Return only top N features by importance (optional)",
                },
            },
            "required": ["symbol", "features"],
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOL_DEFINITIONS


# ---------------------------------------------------------------------------
# Tool dispatch (call_tool)
# ---------------------------------------------------------------------------

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Route tool calls to implementations."""
    try:
        result = await _dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, default=str))]
    except Exception as e:
        logger.error("Tool %s failed: %s", name, e)
        error_detail = {
            "error": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc(),
        }
        return [TextContent(type="text", text=json.dumps(error_detail))]


async def _dispatch(name: str, arguments: dict):
    """Dispatch a tool call to its implementation."""
    if name == "predict":
        from qitp_mcp_ml_predict.tools.predict import predict

        return await predict(
            symbol=arguments["symbol"],
            features=arguments["features"],
            horizons=arguments.get("horizons", ["T+1", "T+3", "T+5"]),
            model_id=arguments.get("model_id", "gap_direction_xgb"),
        )

    elif name == "get_model_metadata":
        from qitp_mcp_ml_predict.tools.metadata import get_model_metadata

        return await get_model_metadata(
            model_id=arguments.get("model_id", "gap_direction_xgb"),
            horizon=arguments.get("horizon"),
        )

    elif name == "get_feature_importance":
        from qitp_mcp_ml_predict.tools.explainability import get_feature_importance

        return await get_feature_importance(
            symbol=arguments["symbol"],
            features=arguments["features"],
            horizon=arguments.get("horizon", "T+1"),
            model_id=arguments.get("model_id", "gap_direction_xgb"),
            top_n=arguments.get("top_n"),
        )

    else:
        raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def run_stdio():
    """Run MCP server over stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    """Main entrypoint — select transport based on env."""
    import asyncio

    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()

    if transport == "stdio":
        asyncio.run(run_stdio())
    elif transport == "http":
        from mcp.server.streamable_http import StreamableHTTPServer

        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_PORT", "8080"))
        logger.info("Starting HTTP transport on %s:%d", host, port)
        http_server = StreamableHTTPServer(server, host=host, port=port)
        asyncio.run(http_server.run())
    else:
        logger.error("Unknown MCP_TRANSPORT=%s. Use 'stdio' or 'http'.", transport)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

### `Dockerfile`

```dockerfile
FROM python:3.12-slim AS base

WORKDIR /app

# Install system deps (libgomp needed for XGBoost)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install package
RUN pip install --no-cache-dir .

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default: HTTP transport for production
ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8080
ENV EXECUTION_MODE=backtest
ENV S3_MODEL_ARTIFACTS_BUCKET=qitp-model-artifacts

EXPOSE 8080

ENTRYPOINT ["ml-predict-mcp"]
```

---

### `docker-compose.yml`

```yaml
version: "3.9"

services:
  ml-predict-mcp:
    build: .
    container_name: qitp-ml-predict-mcp
    ports:
      - "8008:8080"
    environment:
      - MCP_TRANSPORT=http
      - MCP_HOST=0.0.0.0
      - MCP_PORT=8080
      - EXECUTION_MODE=${EXECUTION_MODE:-backtest}
      - S3_MODEL_ARTIFACTS_BUCKET=${S3_MODEL_ARTIFACTS_BUCKET:-qitp-model-artifacts}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-eu-west-1}
      - SAGEMAKER_REGION=${SAGEMAKER_REGION:-us-west-2}
      - SAGEMAKER_ROLE_ARN=${SAGEMAKER_ROLE_ARN:-}
    restart: unless-stopped
    networks:
      - qitp

networks:
  qitp:
    driver: bridge
```

---

## Tests

---

### `tests/conftest.py`

```python
"""Shared test fixtures for ML prediction MCP server tests."""

from __future__ import annotations

import io
import json
import os
import tempfile
from datetime import date
from unittest.mock import MagicMock

import joblib
import numpy as np
import pytest
from sklearn.datasets import make_classification
from xgboost import XGBClassifier

from qitp_mcp_ml_predict.model import loader as model_loader
from qitp_mcp_ml_predict.schemas import FeatureVector


@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    """Default all tests to backtest mode with test bucket."""
    monkeypatch.setenv("EXECUTION_MODE", "backtest")
    monkeypatch.setenv("S3_MODEL_ARTIFACTS_BUCKET", "test-model-artifacts")


@pytest.fixture(autouse=True)
def _clear_model_cache():
    """Clear model cache before each test."""
    model_loader.clear_cache()
    yield
    model_loader.clear_cache()


@pytest.fixture
def sample_features() -> dict:
    """Sample feature dict for testing."""
    return {
        "gap_pct": 3.5,
        "volume_ratio": 1.8,
        "sentiment_score": 0.6,
        "vix_level": 18.5,
        "sector_encoded": 0,
        "prior_week_return": 2.1,
        "analyst_revision": 3.0,
    }


@pytest.fixture
def sample_feature_vector(sample_features) -> FeatureVector:
    """Sample FeatureVector for testing."""
    return FeatureVector(**sample_features)


@pytest.fixture
def trained_xgb_model() -> XGBClassifier:
    """A trained XGBoost classifier for testing.

    Generates synthetic data resembling gap trading features and trains
    a small model. Deterministic via random_state.
    """
    X, y = make_classification(
        n_samples=200,
        n_features=7,
        n_informative=5,
        n_redundant=1,
        n_classes=2,
        random_state=42,
    )
    model = XGBClassifier(
        n_estimators=10,
        max_depth=3,
        random_state=42,
        use_label_encoder=False,
        eval_metric="logloss",
    )
    model.fit(X, y)
    return model


@pytest.fixture
def model_joblib_bytes(trained_xgb_model) -> bytes:
    """Serialize trained model to joblib bytes."""
    with tempfile.NamedTemporaryFile(suffix=".joblib", delete=True) as tmp:
        joblib.dump(trained_xgb_model, tmp.name)
        tmp.seek(0)
        return open(tmp.name, "rb").read()


@pytest.fixture
def sample_metadata() -> dict:
    """Sample model metadata dict."""
    return {
        "model_id": "gap_direction_xgb_t1",
        "version": "v1",
        "training_date": "2026-01-15",
        "training_data_start": "2024-01-01",
        "training_data_end": "2025-12-31",
        "horizons": ["t1"],
        "feature_names": FeatureVector.feature_names(),
        "metrics": {
            "accuracy": 0.72,
            "auc_roc": 0.78,
            "brier_score": 0.19,
            "precision_up": 0.74,
            "recall_up": 0.70,
            "precision_down": 0.69,
            "recall_down": 0.73,
            "f1_macro": 0.71,
            "sample_count": 40,
        },
        "s3_path": "s3://test-model-artifacts/gap_direction_xgb_t1/v1/",
        "description": "Test model for T+1 horizon",
    }


@pytest.fixture
def mock_s3_client(model_joblib_bytes, sample_metadata):
    """Mock boto3 S3 client that serves model artifacts."""
    client = MagicMock()

    class NoSuchKey(Exception):
        pass

    client.exceptions = MagicMock()
    client.exceptions.NoSuchKey = NoSuchKey

    def get_object(Bucket, Key):
        # Serve model joblib for any model variant
        if Key.endswith("model.joblib"):
            body = MagicMock()
            body.read.return_value = model_joblib_bytes
            return {"Body": body}
        # Serve metadata
        elif Key.endswith("metadata.json"):
            body = MagicMock()
            body.read.return_value = json.dumps(sample_metadata).encode("utf-8")
            return {"Body": body}
        # Serve latest version pointer
        elif Key.endswith("latest"):
            body = MagicMock()
            body.read.return_value = b"v1"
            return {"Body": body}
        raise NoSuchKey(f"Not found: {Key}")

    client.get_object = MagicMock(side_effect=get_object)
    client.put_object = MagicMock(return_value={})
    return client


@pytest.fixture(autouse=True)
def _override_s3(mock_s3_client):
    """Override S3 client in model loader for all tests."""
    model_loader._override_s3_client(mock_s3_client)
    yield
    model_loader._override_s3_client(None)


@pytest.fixture
def sample_training_records() -> list[dict]:
    """Sample training records for pipeline tests."""
    records = []
    np.random.seed(42)
    for i in range(100):
        gap_pct = np.random.uniform(-8, 8)
        volume_ratio = np.random.uniform(0.5, 3.0)
        sentiment = np.random.uniform(-1, 1)
        vix = np.random.uniform(12, 35)
        sector = np.random.randint(0, 11)
        prior_return = np.random.uniform(-10, 10)
        analyst_rev = np.random.uniform(-10, 10)

        # Simplistic outcome: UP if gap + sentiment > 0
        signal = gap_pct * 0.5 + sentiment * 2 + np.random.normal(0, 1)
        outcome = 1 if signal > 0 else 0

        records.append({
            "symbol": f"SYM{i % 10}",
            "date": date(2025, 1, 6 + (i % 20)),
            "gap_pct": round(gap_pct, 4),
            "volume_ratio": round(volume_ratio, 4),
            "sentiment_score": round(sentiment, 4),
            "vix_level": round(vix, 2),
            "sector_encoded": sector,
            "prior_week_return": round(prior_return, 4),
            "analyst_revision": round(analyst_rev, 2),
            "outcome_t1": outcome,
            "outcome_t3": outcome,  # Simplified: same outcome for all horizons in test
            "outcome_t5": outcome,
        })
    return records
```

---

### `tests/test_predict.py`

```python
"""Tests for prediction and inference."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

from qitp_mcp_ml_predict.model.features import (
    build_feature_vector,
    build_feature_vector_from_dict,
    encode_sector,
    features_to_numpy,
    validate_feature_ranges,
)
from qitp_mcp_ml_predict.model.inference import (
    _classify_direction,
    _compute_ml_score,
    compute_shap_values,
    predict,
)
from qitp_mcp_ml_predict.schemas import FeatureVector, HorizonPrediction
from qitp_mcp_ml_predict.tools.predict import predict as predict_tool


# ---------------------------------------------------------------------------
# Feature vector tests
# ---------------------------------------------------------------------------


class TestFeatureVector:
    def test_to_array_order(self, sample_feature_vector):
        """Feature array must follow the canonical order."""
        arr = sample_feature_vector.to_array()
        assert len(arr) == 7
        assert arr[0] == 3.5   # gap_pct
        assert arr[1] == 1.8   # volume_ratio
        assert arr[2] == 0.6   # sentiment_score
        assert arr[3] == 18.5  # vix_level
        assert arr[4] == 0.0   # sector_encoded
        assert arr[5] == 2.1   # prior_week_return
        assert arr[6] == 3.0   # analyst_revision

    def test_feature_names_match_array(self):
        """Feature names must match to_array() order."""
        names = FeatureVector.feature_names()
        assert names == [
            "gap_pct", "volume_ratio", "sentiment_score",
            "vix_level", "sector_encoded", "prior_week_return", "analyst_revision",
        ]

    def test_build_from_dict(self, sample_features):
        """Build FeatureVector from a raw dict."""
        fv = build_feature_vector_from_dict(sample_features)
        assert fv.gap_pct == 3.5
        assert fv.sector_encoded == 0

    def test_build_from_dict_with_sector_name(self):
        """Build FeatureVector when sector is a string name."""
        data = {
            "gap_pct": 2.0,
            "volume_ratio": 1.5,
            "sentiment_score": 0.3,
            "vix_level": 20.0,
            "sector": "Healthcare",
            "prior_week_return": 1.0,
            "analyst_revision": 0.0,
        }
        fv = build_feature_vector_from_dict(data)
        assert fv.sector_encoded == 1  # Healthcare = 1

    def test_sentiment_clamped(self):
        """Sentiment should be clamped to [-1, 1]."""
        fv = build_feature_vector(
            gap_pct=1.0, volume_ratio=1.0, sentiment_score=5.0,
            vix_level=20.0, sector=0, prior_week_return=0.0, analyst_revision=0.0,
        )
        assert fv.sentiment_score == 1.0

    def test_features_to_numpy_shape(self, sample_feature_vector):
        """Numpy output must be (1, 7)."""
        X = features_to_numpy(sample_feature_vector)
        assert X.shape == (1, 7)
        assert X.dtype == np.float64


class TestSectorEncoding:
    def test_known_sectors(self):
        assert encode_sector("Technology") == 0
        assert encode_sector("Healthcare") == 1
        assert encode_sector("Energy") == 5
        assert encode_sector("Communication Services") == 10

    def test_unknown_sector_defaults_to_zero(self):
        assert encode_sector("Unknown Sector") == 0


class TestFeatureValidation:
    def test_normal_features_no_warnings(self, sample_feature_vector):
        warnings = validate_feature_ranges(sample_feature_vector)
        assert warnings == []

    def test_extreme_gap_warns(self):
        fv = FeatureVector(
            gap_pct=25.0, volume_ratio=1.0, sentiment_score=0.0,
            vix_level=20.0, sector_encoded=0, prior_week_return=0.0,
            analyst_revision=0.0,
        )
        warnings = validate_feature_ranges(fv)
        assert any("gap_pct" in w for w in warnings)

    def test_extreme_volume_warns(self):
        fv = FeatureVector(
            gap_pct=2.0, volume_ratio=15.0, sentiment_score=0.0,
            vix_level=20.0, sector_encoded=0, prior_week_return=0.0,
            analyst_revision=0.0,
        )
        warnings = validate_feature_ranges(fv)
        assert any("volume_ratio" in w for w in warnings)


# ---------------------------------------------------------------------------
# Direction classification tests
# ---------------------------------------------------------------------------


class TestDirectionClassification:
    def test_high_prob_up(self):
        assert _classify_direction(0.80) == "UP"

    def test_high_prob_down(self):
        assert _classify_direction(0.20) == "DOWN"

    def test_neutral_zone(self):
        assert _classify_direction(0.50) == "NEUTRAL"

    def test_boundary_up(self):
        assert _classify_direction(0.55) == "UP"

    def test_boundary_down(self):
        assert _classify_direction(0.45) == "DOWN"


class TestMLScore:
    def test_all_up(self):
        preds = [
            HorizonPrediction(horizon="T+1", direction="UP", probability_up=0.8, probability_down=0.2, confidence=0.8),
            HorizonPrediction(horizon="T+3", direction="UP", probability_up=0.7, probability_down=0.3, confidence=0.7),
            HorizonPrediction(horizon="T+5", direction="UP", probability_up=0.6, probability_down=0.4, confidence=0.6),
        ]
        score = _compute_ml_score(preds)
        assert score > 0.0  # Should be bullish

    def test_all_down(self):
        preds = [
            HorizonPrediction(horizon="T+1", direction="DOWN", probability_up=0.2, probability_down=0.8, confidence=0.8),
            HorizonPrediction(horizon="T+3", direction="DOWN", probability_up=0.3, probability_down=0.7, confidence=0.7),
            HorizonPrediction(horizon="T+5", direction="DOWN", probability_up=0.4, probability_down=0.6, confidence=0.6),
        ]
        score = _compute_ml_score(preds)
        assert score < 0.0  # Should be bearish

    def test_neutral_mixed(self):
        preds = [
            HorizonPrediction(horizon="T+1", direction="UP", probability_up=0.6, probability_down=0.4, confidence=0.6),
            HorizonPrediction(horizon="T+3", direction="DOWN", probability_up=0.4, probability_down=0.6, confidence=0.6),
            HorizonPrediction(horizon="T+5", direction="NEUTRAL", probability_up=0.5, probability_down=0.5, confidence=0.5),
        ]
        score = _compute_ml_score(preds)
        assert -0.3 < score < 0.3  # Should be near neutral

    def test_empty_predictions(self):
        assert _compute_ml_score([]) == 0.0

    def test_score_bounded(self):
        """ML score must be in [-1, 1]."""
        preds = [
            HorizonPrediction(horizon="T+1", direction="UP", probability_up=1.0, probability_down=0.0, confidence=1.0),
            HorizonPrediction(horizon="T+3", direction="UP", probability_up=1.0, probability_down=0.0, confidence=1.0),
            HorizonPrediction(horizon="T+5", direction="UP", probability_up=1.0, probability_down=0.0, confidence=1.0),
        ]
        score = _compute_ml_score(preds)
        assert -1.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Inference tests (integration with mock S3 model)
# ---------------------------------------------------------------------------


class TestPredict:
    def test_predict_returns_all_horizons(self, sample_feature_vector):
        """Predict should return results for all requested horizons."""
        result = predict("AAPL", sample_feature_vector)

        assert result.symbol == "AAPL"
        assert len(result.predictions) == 3
        horizons_returned = {p.horizon for p in result.predictions}
        assert horizons_returned == {"T+1", "T+3", "T+5"}

    def test_predict_single_horizon(self, sample_feature_vector):
        """Predict should work with a single horizon."""
        result = predict("AAPL", sample_feature_vector, horizons=["T+1"])

        assert len(result.predictions) == 1
        assert result.predictions[0].horizon == "T+1"

    def test_predict_directions_valid(self, sample_feature_vector):
        """All directions must be UP, DOWN, or NEUTRAL."""
        result = predict("AAPL", sample_feature_vector)

        for pred in result.predictions:
            assert pred.direction in ("UP", "DOWN", "NEUTRAL")

    def test_predict_probabilities_sum_to_one(self, sample_feature_vector):
        """prob_up + prob_down should approximately equal 1.0."""
        result = predict("AAPL", sample_feature_vector)

        for pred in result.predictions:
            total = pred.probability_up + pred.probability_down
            assert abs(total - 1.0) < 0.01

    def test_predict_confidence_range(self, sample_feature_vector):
        """Confidence must be in [0.5, 1.0] (it's the max of the two probabilities)."""
        result = predict("AAPL", sample_feature_vector)

        for pred in result.predictions:
            assert 0.5 <= pred.confidence <= 1.0

    def test_predict_ml_score_bounded(self, sample_feature_vector):
        """ml_score must be in [-1, 1]."""
        result = predict("AAPL", sample_feature_vector)
        assert -1.0 <= result.ml_score <= 1.0

    def test_predict_overall_direction(self, sample_feature_vector):
        """Overall direction must be a valid value."""
        result = predict("AAPL", sample_feature_vector)
        assert result.overall_direction in ("UP", "DOWN", "NEUTRAL")


class TestSHAPExplainability:
    def test_shap_returns_all_features(self, sample_feature_vector):
        """SHAP explanation should cover all 7 features."""
        result = compute_shap_values(sample_feature_vector)

        assert len(result.feature_importances) == 7

    def test_shap_features_ranked_by_importance(self, sample_feature_vector):
        """Features should be sorted by abs(SHAP value) descending."""
        result = compute_shap_values(sample_feature_vector)

        abs_vals = [fi.abs_shap_value for fi in result.feature_importances]
        assert abs_vals == sorted(abs_vals, reverse=True)

    def test_shap_values_sum_approximately(self, sample_feature_vector):
        """base_value + sum(SHAP values) should approximately equal prediction_value."""
        result = compute_shap_values(sample_feature_vector)

        shap_sum = sum(fi.shap_value for fi in result.feature_importances)
        expected = result.base_value + shap_sum
        assert abs(expected - result.prediction_value) < 0.01

    def test_shap_direction_contributions(self, sample_feature_vector):
        """Each feature should have a valid direction contribution."""
        result = compute_shap_values(sample_feature_vector)

        for fi in result.feature_importances:
            assert fi.direction_contribution in ("bullish", "bearish", "neutral")


# ---------------------------------------------------------------------------
# Tool-level tests
# ---------------------------------------------------------------------------


class TestPredictTool:
    @pytest.mark.asyncio
    async def test_predict_tool_returns_dict(self, sample_features):
        """The predict tool should return a JSON-serializable dict."""
        result = await predict_tool("AAPL", sample_features)

        assert isinstance(result, dict)
        assert result["symbol"] == "AAPL"
        assert "predictions" in result
        assert "ml_score" in result
        assert "overall_direction" in result

    @pytest.mark.asyncio
    async def test_predict_tool_custom_horizons(self, sample_features):
        """The predict tool should respect custom horizons."""
        result = await predict_tool("AAPL", sample_features, horizons=["T+1"])

        assert len(result["predictions"]) == 1
        assert result["predictions"][0]["horizon"] == "T+1"
```

---

### `tests/test_features.py`

```python
"""Tests for feature engineering and composite score."""

from __future__ import annotations

import numpy as np
import pytest

from qitp_mcp_ml_predict.composite_score import (
    WEIGHTS,
    compute_composite_score,
    normalize_ml_score_to_unit,
)
from qitp_mcp_ml_predict.model.features import (
    SECTOR_ENCODING,
    build_feature_vector,
    build_feature_vector_from_dict,
    encode_sector,
    features_to_numpy,
)
from qitp_mcp_ml_predict.schemas import CompositeScoreInput, FeatureVector


# ---------------------------------------------------------------------------
# Composite score tests
# ---------------------------------------------------------------------------


class TestCompositeScore:
    def test_weights_sum_to_one(self):
        """Composite weights must sum to 1.0."""
        total = sum(WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_all_ones_gives_one(self):
        """All scores at 1.0 should produce composite of 1.0."""
        result = compute_composite_score(
            CompositeScoreInput(
                gap_score=1.0,
                sentiment_score=1.0,
                technical_score=1.0,
                ml_score=1.0,
            )
        )
        assert abs(result.composite_score - 1.0) < 0.001

    def test_all_zeros_gives_zero(self):
        """All scores at 0.0 should produce composite of 0.0."""
        result = compute_composite_score(
            CompositeScoreInput(
                gap_score=0.0,
                sentiment_score=0.0,
                technical_score=0.0,
                ml_score=0.0,
            )
        )
        assert result.composite_score == 0.0

    def test_gap_has_highest_weight(self):
        """Gap score should have the largest single impact."""
        # Only gap at 1.0
        gap_only = compute_composite_score(
            CompositeScoreInput(gap_score=1.0, sentiment_score=0.0, technical_score=0.0, ml_score=0.0)
        )
        # Only sentiment at 1.0
        sent_only = compute_composite_score(
            CompositeScoreInput(gap_score=0.0, sentiment_score=1.0, technical_score=0.0, ml_score=0.0)
        )
        assert gap_only.composite_score > sent_only.composite_score

    def test_ml_weight_is_twenty_percent(self):
        """ML contribution should be exactly 20% of ml_score."""
        result = compute_composite_score(
            CompositeScoreInput(gap_score=0.0, sentiment_score=0.0, technical_score=0.0, ml_score=1.0)
        )
        assert abs(result.composite_score - 0.20) < 0.001
        assert abs(result.component_contributions["ml"] - 0.20) < 0.001

    def test_signal_strength_strong(self):
        result = compute_composite_score(
            CompositeScoreInput(gap_score=0.9, sentiment_score=0.8, technical_score=0.7, ml_score=0.8)
        )
        assert result.signal_strength == "strong"

    def test_signal_strength_moderate(self):
        result = compute_composite_score(
            CompositeScoreInput(gap_score=0.5, sentiment_score=0.5, technical_score=0.5, ml_score=0.5)
        )
        assert result.signal_strength == "moderate"

    def test_signal_strength_weak(self):
        result = compute_composite_score(
            CompositeScoreInput(gap_score=0.2, sentiment_score=0.1, technical_score=0.1, ml_score=0.1)
        )
        assert result.signal_strength == "weak"

    def test_component_contributions_sum(self):
        """Component contributions should sum to composite_score."""
        result = compute_composite_score(
            CompositeScoreInput(gap_score=0.8, sentiment_score=0.6, technical_score=0.7, ml_score=0.5)
        )
        contrib_sum = sum(result.component_contributions.values())
        assert abs(contrib_sum - result.composite_score) < 0.001


class TestNormalizeMLScore:
    def test_positive_one_maps_to_one(self):
        assert normalize_ml_score_to_unit(1.0) == 1.0

    def test_negative_one_maps_to_zero(self):
        assert normalize_ml_score_to_unit(-1.0) == 0.0

    def test_zero_maps_to_half(self):
        assert normalize_ml_score_to_unit(0.0) == 0.5

    def test_clamped_above(self):
        assert normalize_ml_score_to_unit(2.0) == 1.0

    def test_clamped_below(self):
        assert normalize_ml_score_to_unit(-2.0) == 0.0


# ---------------------------------------------------------------------------
# Sector encoding completeness
# ---------------------------------------------------------------------------


class TestSectorEncodingCompleteness:
    def test_all_gics_sectors_covered(self):
        """All 11 GICS sectors should be in the encoding map."""
        expected_sectors = {
            "Technology", "Healthcare", "Financials",
            "Consumer Discretionary", "Consumer Staples", "Energy",
            "Industrials", "Materials", "Utilities",
            "Real Estate", "Communication Services",
        }
        assert set(SECTOR_ENCODING.keys()) == expected_sectors

    def test_unique_codes(self):
        """All sector codes should be unique."""
        codes = list(SECTOR_ENCODING.values())
        assert len(codes) == len(set(codes))

    def test_codes_in_range(self):
        """All codes should be in [0, 10]."""
        for code in SECTOR_ENCODING.values():
            assert 0 <= code <= 10
```

---

### `tests/test_training.py`

```python
"""Tests for the training pipeline."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from qitp_mcp_ml_predict.training.data_prep import (
    build_training_record,
    compute_outcome,
    prepare_training_dataframe,
    split_features_labels,
)
from qitp_mcp_ml_predict.training.pipeline import (
    _evaluate_model,
    run_full_pipeline,
    train_horizon_model,
)


# ---------------------------------------------------------------------------
# Data preparation tests
# ---------------------------------------------------------------------------


class TestComputeOutcome:
    def test_up_outcome(self):
        assert compute_outcome(monday_open=100.0, future_close=105.0) == 1

    def test_down_outcome(self):
        assert compute_outcome(monday_open=100.0, future_close=95.0) == 0

    def test_flat_is_down(self):
        """Equal prices count as DOWN (not strictly higher)."""
        assert compute_outcome(monday_open=100.0, future_close=100.0) == 0


class TestBuildTrainingRecord:
    def test_record_has_all_fields(self):
        record = build_training_record(
            symbol="AAPL",
            monday_date=date(2025, 1, 13),
            gap_pct=3.5,
            volume_ratio=1.8,
            sentiment_score=0.6,
            vix_level=18.5,
            sector_encoded=0,
            prior_week_return=2.1,
            analyst_revision=3.0,
            outcome_t1=1,
            outcome_t3=1,
            outcome_t5=0,
        )
        assert record["symbol"] == "AAPL"
        assert record["gap_pct"] == 3.5
        assert record["outcome_t1"] == 1
        assert record["outcome_t5"] == 0
        assert len(record) == 12  # 2 metadata + 7 features + 3 outcomes


class TestPrepareTrainingDataframe:
    def test_basic_preparation(self, sample_training_records):
        df = prepare_training_dataframe(sample_training_records)

        assert not df.empty
        assert "gap_pct" in df.columns
        assert "outcome_t1" in df.columns
        # Should have filtered out very small gaps
        assert (df["gap_pct"].abs() >= 0.5).all()

    def test_drops_nan_features(self):
        records = [
            {
                "symbol": "TEST", "date": date(2025, 1, 13),
                "gap_pct": None, "volume_ratio": 1.0, "sentiment_score": 0.0,
                "vix_level": 20.0, "sector_encoded": 0,
                "prior_week_return": 0.0, "analyst_revision": 0.0,
                "outcome_t1": 1, "outcome_t3": 1, "outcome_t5": 1,
            },
            {
                "symbol": "TEST", "date": date(2025, 1, 13),
                "gap_pct": 3.0, "volume_ratio": 1.0, "sentiment_score": 0.0,
                "vix_level": 20.0, "sector_encoded": 0,
                "prior_week_return": 0.0, "analyst_revision": 0.0,
                "outcome_t1": 1, "outcome_t3": 1, "outcome_t5": 1,
            },
        ]
        df = prepare_training_dataframe(records)
        assert len(df) == 1  # First record dropped due to NaN

    def test_empty_records(self):
        df = prepare_training_dataframe([])
        assert df.empty


class TestSplitFeaturesLabels:
    def test_split_t1(self, sample_training_records):
        df = prepare_training_dataframe(sample_training_records)
        X, y = split_features_labels(df, "t1")

        assert X.shape[1] == 7
        assert len(y) == len(df)
        assert set(np.unique(y)).issubset({0, 1})

    def test_split_t3(self, sample_training_records):
        df = prepare_training_dataframe(sample_training_records)
        X, y = split_features_labels(df, "t3")

        assert X.shape[1] == 7

    def test_invalid_horizon_raises(self, sample_training_records):
        df = prepare_training_dataframe(sample_training_records)
        with pytest.raises(ValueError, match="Label column"):
            split_features_labels(df, "t99")


# ---------------------------------------------------------------------------
# Training pipeline tests
# ---------------------------------------------------------------------------


class TestTrainHorizonModel:
    def test_train_produces_model_and_metrics(self, sample_training_records):
        """Training should produce a model, metrics, and S3 path."""
        model, metrics, s3_path = train_horizon_model(
            records=sample_training_records,
            horizon="t1",
            model_id="test_model",
            version="v1",
            params={
                "n_estimators": 10,
                "max_depth": 3,
                "random_state": 42,
                "use_label_encoder": False,
                "eval_metric": "logloss",
            },
        )

        assert model is not None
        assert hasattr(model, "predict_proba")
        assert 0.0 <= metrics.accuracy <= 1.0
        assert 0.0 <= metrics.auc_roc <= 1.0
        assert 0.0 <= metrics.brier_score <= 1.0
        assert metrics.sample_count > 0
        assert "s3://" in s3_path

    def test_train_insufficient_data_raises(self):
        """Training with too few records should raise."""
        records = [
            {
                "symbol": "TEST", "date": date(2025, 1, 13),
                "gap_pct": 3.0, "volume_ratio": 1.0, "sentiment_score": 0.0,
                "vix_level": 20.0, "sector_encoded": 0,
                "prior_week_return": 0.0, "analyst_revision": 0.0,
                "outcome_t1": 1, "outcome_t3": 1, "outcome_t5": 1,
            }
        ] * 10  # Only 10 records (below 50 minimum)

        with pytest.raises(ValueError, match="Insufficient training data"):
            train_horizon_model(
                records=records,
                horizon="t1",
                model_id="test_model",
                version="v1",
            )


class TestFullPipeline:
    def test_full_pipeline_runs_all_horizons(self, sample_training_records):
        """Full pipeline should train models for t1, t3, t5."""
        results = run_full_pipeline(
            records=sample_training_records,
            model_id="test_model",
            version="v1",
            params={
                "n_estimators": 10,
                "max_depth": 3,
                "random_state": 42,
                "use_label_encoder": False,
                "eval_metric": "logloss",
            },
        )

        assert results["overall_status"] == "success"
        assert "t1" in results["horizons"]
        assert "t3" in results["horizons"]
        assert "t5" in results["horizons"]

        for horizon in ["t1", "t3", "t5"]:
            assert results["horizons"][horizon]["status"] == "success"
            assert "metrics" in results["horizons"][horizon]
            assert "s3_path" in results["horizons"][horizon]


# ---------------------------------------------------------------------------
# Model evaluation tests
# ---------------------------------------------------------------------------


class TestEvaluateModel:
    def test_evaluation_metrics_range(self, trained_xgb_model):
        """All evaluation metrics should be in valid ranges."""
        from sklearn.datasets import make_classification

        X_test, y_test = make_classification(
            n_samples=50, n_features=7, n_informative=5,
            n_classes=2, random_state=99,
        )
        metrics = _evaluate_model(trained_xgb_model, X_test, y_test)

        assert 0.0 <= metrics.accuracy <= 1.0
        assert 0.0 <= metrics.auc_roc <= 1.0
        assert 0.0 <= metrics.brier_score <= 1.0
        assert 0.0 <= metrics.f1_macro <= 1.0
        assert metrics.sample_count == 50
```

---

### `tests/fixtures/sample_features.json`

```json
{
  "symbol": "AAPL",
  "features": {
    "gap_pct": 3.5,
    "volume_ratio": 1.8,
    "sentiment_score": 0.6,
    "vix_level": 18.5,
    "sector_encoded": 0,
    "prior_week_return": 2.1,
    "analyst_revision": 3.0
  },
  "horizons": ["T+1", "T+3", "T+5"],
  "model_id": "gap_direction_xgb"
}
```

---

## Agent Handler (in tccw-qitp-agents)

---

### `blueprints/agents/ml_predictor.yaml`

```yaml
agent_id: ml-predictor
name: ML Prediction Agent
version: "1.0.0"
description: >
  Single-agent pattern that runs XGBoost inference for a set of symbols,
  collects SHAP explanations, and produces an ML prediction report artifact.
  Updates composite scores with the ML weight (20%).

model:
  provider: anthropic
  model_id: claude-sonnet-4-20250514
  max_tokens: 4096
  temperature: 0.1

system_prompt_id: ml-predictor-system-v1

tools:
  - name: ml-predict-mcp
    type: mcp
    uri: "${ML_PREDICT_MCP_URI}"
    operations:
      - predict
      - get_model_metadata
      - get_feature_importance
  - name: market-data-mcp
    type: mcp
    uri: "${MARKET_DATA_MCP_URI}"
    operations:
      - get_ohlcv
      - get_volume_profile
  - name: artifacts-mcp
    type: mcp
    uri: "${ARTIFACTS_MCP_URI}"
    operations:
      - create_artifact
      - get_artifact

execution:
  timeout_seconds: 90
  max_tool_calls: 80
  retry_policy:
    max_retries: 2
    backoff_base: 1.0

output_schema: MLPredictionReport

tags:
  - ml-prediction
  - xgboost
  - phase-2
```

---

### `src/qitp_agents/ml_predictor/__init__.py`

```python
"""ML Prediction Agent — XGBoost inference with SHAP explainability."""
```

---

### `src/qitp_agents/ml_predictor/handler.py`

```python
"""ML Prediction Agent Lambda handler.

Input:  {
    "symbols": ["AAPL", "TSLA", ...],
    "date": "2026-03-15",
    "features_by_symbol": {
        "AAPL": {"gap_pct": 3.5, "volume_ratio": 1.8, ...},
        "TSLA": {"gap_pct": -2.1, "volume_ratio": 2.5, ...}
    },
    "gap_results_artifact_id": "...",
    "sentiment_results_artifact_id": "..."
}
Output: MLPredictionReport JSON artifact with per-symbol predictions, SHAP explanations,
        and updated composite scores.

Architecture:
- Single Strands agent (no multi-agent pattern)
- Tools: ml-predict-mcp (predict, get_feature_importance, get_model_metadata)
- Tools: market-data-mcp (get_ohlcv, get_volume_profile) for feature enrichment
- Tools: artifacts-mcp (create_artifact, get_artifact) for input/output storage
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from agent_core.blueprint import BlueprintLoader
from agent_core.models.execution import ExecutionMode

logger = logging.getLogger(__name__)

# --- Warm-start initialization (outside handler) ---
EXECUTION_MODE = ExecutionMode(os.environ.get("EXECUTION_MODE", "lambda"))
LOADER = BlueprintLoader(blueprints_dir=os.environ.get("BLUEPRINTS_DIR", "blueprints"))

AGENT_ID = "ml-predictor"
MAX_OUTPUT_BYTES = 256 * 1024  # 256KB claim-check threshold


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Lambda handler for ML Prediction Agent.

    Args:
        event: Input payload with symbols, date, features_by_symbol, and optional
               artifact references from prior pipeline stages.
        context: Lambda context (optional).

    Returns:
        JSON response with ML prediction report or claim-check reference.
    """
    logger.info(
        "ML predictor invoked",
        extra={"symbol_count": len(event.get("symbols", []))},
    )

    symbols = event.get("symbols", [])
    date_str = event.get("date")
    features_by_symbol = event.get("features_by_symbol", {})
    gap_artifact_id = event.get("gap_results_artifact_id")
    sentiment_artifact_id = event.get("sentiment_results_artifact_id")

    if not symbols:
        return _error_response("Missing required field: symbols")
    if not date_str:
        return _error_response("Missing required field: date")

    try:
        mcp_clients = _create_mcp_clients()

        # Build agent from blueprint
        agent = LOADER.build_strands_agent(AGENT_ID, mcp_clients)

        # Build features context
        features_json = json.dumps(features_by_symbol, indent=2) if features_by_symbol else "Not provided"
        symbols_str = ", ".join(symbols)

        prompt = (
            f"Generate ML predictions for the following symbols on {date_str}: {symbols_str}\n\n"
            f"## Pre-computed Features\n"
            f"{features_json}\n\n"
            f"## Instructions\n"
            f"For each symbol:\n"
            f"1. If features are provided in features_by_symbol, use them directly.\n"
            f"   If not, construct features by:\n"
            f"   a. Calling get_ohlcv to compute gap_pct and prior_week_return\n"
            f"   b. Calling get_volume_profile for volume_ratio\n"
            f"   c. Using sentiment data from artifact {sentiment_artifact_id or 'N/A'}\n"
            f"2. Call predict(symbol, features) to get T+1, T+3, T+5 predictions.\n"
            f"3. Call get_feature_importance(symbol, features) for SHAP explanation.\n"
            f"4. Record: symbol, predictions, shap_top_3_features, ml_score.\n\n"
            f"After all symbols:\n"
            f"5. Call get_model_metadata() to include model version in the report.\n"
            f"6. Create an MLPredictionReport artifact with:\n"
            f"   - model_version, prediction_date\n"
            f"   - per_symbol_predictions: list of (symbol, direction, confidence, ml_score, top_shap_features)\n"
            f"   - symbols_bullish: symbols with overall_direction=UP and confidence > 0.6\n"
            f"   - symbols_bearish: symbols with overall_direction=DOWN and confidence > 0.6\n"
            f"   - composite_score_updates: for each symbol, the ml_score to feed into composite formula\n"
            f"7. Return the artifact ID and the full report.\n"
        )

        if gap_artifact_id:
            prompt += f"\nContext: Gap detection results in artifact {gap_artifact_id}.\n"
        if sentiment_artifact_id:
            prompt += f"Context: Sentiment results in artifact {sentiment_artifact_id}.\n"

        result = agent(prompt)

        output = _marshal_output(result)
        return _success_response(output)

    except Exception as e:
        logger.exception("ML predictor failed")
        return _error_response(str(e))


def _create_mcp_clients() -> dict[str, Any]:
    """Create MCP client instances for this invocation."""
    from agent_core.mcp import create_mcp_client

    clients = {}

    ml_predict_uri = os.environ.get("ML_PREDICT_MCP_URI", "http://localhost:8008")
    clients["ml-predict-mcp"] = create_mcp_client(
        name="ml-predict-mcp",
        uri=ml_predict_uri,
    )

    market_data_uri = os.environ.get("MARKET_DATA_MCP_URI", "http://localhost:8002")
    clients["market-data-mcp"] = create_mcp_client(
        name="market-data-mcp",
        uri=market_data_uri,
    )

    artifacts_uri = os.environ.get("ARTIFACTS_MCP_URI", "http://localhost:8004")
    clients["artifacts-mcp"] = create_mcp_client(
        name="artifacts-mcp",
        uri=artifacts_uri,
    )

    return clients


def _marshal_output(result: Any) -> dict[str, Any]:
    """Marshal agent result to JSON-serializable dict with claim-check for large outputs."""
    if hasattr(result, "model_dump"):
        output = result.model_dump()
    elif isinstance(result, dict):
        output = result
    else:
        output = {"raw_output": str(result)}

    serialized = json.dumps(output)
    if len(serialized.encode("utf-8")) > MAX_OUTPUT_BYTES:
        logger.warning("Output exceeds 256KB, storing claim-check reference")
        output = {
            "claim_check": True,
            "message": "Output exceeded 256KB. Full result stored as artifact.",
            "artifact_id": output.get("artifact_id", "unknown"),
        }

    return output


def _success_response(data: dict[str, Any]) -> dict[str, Any]:
    return {"statusCode": 200, "body": json.dumps(data)}


def _error_response(message: str) -> dict[str, Any]:
    return {"statusCode": 500, "body": json.dumps({"error": message})}
```

---

## Acceptance Criteria

- [ ] MCP server starts and lists 3 tools (`predict`, `get_model_metadata`, `get_feature_importance`)
- [ ] `predict` returns valid direction (UP/DOWN/NEUTRAL) with confidence and probabilities for T+1, T+3, T+5
- [ ] Probabilities per horizon sum to ~1.0 (prob_up + prob_down)
- [ ] `ml_score` is bounded to [-1.0, 1.0]
- [ ] `get_feature_importance` returns SHAP values for all 7 features, ranked by abs(SHAP value) descending
- [ ] SHAP values satisfy: base_value + sum(SHAP values) ~ prediction_value
- [ ] `get_model_metadata` returns version, metrics (accuracy, AUC, Brier), training date, feature list
- [ ] Model loader caches models in memory (no re-download on warm Lambda)
- [ ] Model versioning: S3 layout is `{model_id}/{version}/model.joblib` + `metadata.json` + `latest`
- [ ] Training pipeline produces valid XGBoost models with accuracy > random (>0.5) on synthetic data
- [ ] Composite score weights: gap(35%) + sentiment(25%) + technical(20%) + ml(20%) = 100%
- [ ] Feature vector has exactly 7 features in canonical order
- [ ] Sector encoding covers all 11 GICS sectors
- [ ] Docker build succeeds
- [ ] All tests pass
- [ ] Agent blueprint YAML is valid and references correct tool operations
- [ ] Agent handler follows Lambda warm-start pattern (LOADER and EXECUTION_MODE outside handler)

## Test Plan

```bash
# MCP server tests
cd ~/dev/tccw-qitp-mcp-ml-predict
pip install -e ".[dev]"
pytest -v

# Docker build
docker build -t qitp-mcp-ml-predict .

# Agent handler tests (run from agents repo)
cd ~/dev/tccw-qitp-agents
pip install -e ".[dev]"
pytest tests/unit/test_ml_predictor.py -v
```

## Agent Instructions

This is a Phase 2 MCP server + agent. The ML layer adds predictive signal to the existing gap+sentiment+technical pipeline.

Key implementation notes:
1. **Feature vector order is sacred**: The 7 features must always appear in the same order (gap_pct, volume_ratio, sentiment_score, vix_level, sector_encoded, prior_week_return, analyst_revision). If the order changes between training and inference, predictions will be wrong.
2. **Three horizons, potentially three models**: Each horizon (T+1, T+3, T+5) can have its own trained model variant. The naming convention is `{model_id}_t1`, `{model_id}_t3`, `{model_id}_t5`. Fall back to base model if variant doesn't exist.
3. **SHAP TreeExplainer**: Use `shap.TreeExplainer` (not `KernelExplainer`) for XGBoost — it's exact and fast. Watch for the binary classification case where `shap_values` is a list of two arrays.
4. **Model caching**: The `_model_cache` dict in `loader.py` persists across warm Lambda invocations. Clear it only when explicitly needed (e.g., model version change).
5. **Composite score update**: The old formula was gap(40%) + sentiment(30%) + technical(30%). The new formula is gap(35%) + sentiment(25%) + technical(20%) + ml(20%). The `ml_score` from PredictionResult is in [-1, 1]; use `normalize_ml_score_to_unit()` to convert to [0, 1] before feeding into the composite.
6. **Training pipeline is local-first**: In POC, training runs locally via `pipeline.py`. The `sagemaker_job.py` module is scaffolding for Phase 2 graduation to SageMaker managed training.
7. **Credentials**: `S3_MODEL_ARTIFACTS_BUCKET`, `SAGEMAKER_ROLE_ARN`, and AWS credentials are all via environment variables. Never hardcode.
8. **Idempotency**: Predictions are deterministic for the same features + model version. No side effects in the predict path.
