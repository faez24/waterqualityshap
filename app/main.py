import pickle
import httpx
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
FIREBASE_URL = "https://lora-tes-default-rtdb.asia-southeast1.firebasedatabase.app/faiz.json"
PKL_PATH     = Path(__file__).parent.parent / "mean_shap_per_class.pkl"
FEATURES     = ["pH", "DO", "EC", "TDS"]

# ── Load SHAP PKL ─────────────────────────────────────────────────────────────
with open(PKL_PATH, "rb") as f:
    mean_shap: Dict[str, Dict[str, float]] = pickle.load(f)

logger.info("✅ Loaded mean_shap_per_class.pkl  |  classes: %s", list(mean_shap.keys()))

# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Water Quality SHAP API",
    description=(
        "API analisis kualitas air menggunakan SHAP. "
        "Data sensor (pH, DO, EC, TDS) diambil dari Firebase RTDB LoRa."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────────────────────
def parse_float(val) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def classify_water(pH: float, DO: float, EC: float, TDS: float) -> str:
    """Rule-based classifier sebagai fallback jika label Firebase tidak tersedia."""
    score = 0
    if 6.5 <= pH <= 8.5:
        score += 2
    if DO >= 6.0:
        score += 2
    if EC <= 1.5:
        score += 1
    if TDS <= 500:
        score += 1
    if score >= 5:
        return "Baik"
    elif score >= 3:
        return "Sedang"
    return "Buruk"


def interpret_feature(feat: str, val: float) -> str:
    interpretations = {
        "pH": [
            (lambda v: v < 6.5,  "Terlalu asam (< 6.5)"),
            (lambda v: v > 8.5,  "Terlalu basa (> 8.5)"),
            (lambda v: True,     "Normal (6.5 – 8.5)"),
        ],
        "DO": [
            (lambda v: v < 4.0,  "Sangat rendah – berbahaya (< 4 mg/L)"),
            (lambda v: v < 6.0,  "Rendah – perlu perhatian (4–6 mg/L)"),
            (lambda v: True,     "Cukup (≥ 6 mg/L)"),
        ],
        "EC": [
            (lambda v: v > 2.0,  "Konduktivitas tinggi (> 2 mS/cm)"),
            (lambda v: True,     "Normal (≤ 2 mS/cm)"),
        ],
        "TDS": [
            (lambda v: v > 500,  "TDS tinggi – perlu filtrasi (> 500 ppm)"),
            (lambda v: True,     "Normal (≤ 500 ppm)"),
        ],
    }
    for condition, label in interpretations.get(feat, []):
        if condition(val):
            return label
    return "–"


def compute_shap_analysis(values: Dict[str, float], predicted_class: str) -> Dict[str, Any]:
    """
    Hitung kontribusi SHAP per fitur berdasarkan mean_shap_per_class.pkl
    untuk kelas yang diprediksi.
    """
    shap_for_class = mean_shap.get(predicted_class, {})
    total_abs_shap = sum(abs(v) for v in shap_for_class.values()) or 1.0

    contributions: Dict[str, Any] = {}
    for feat in FEATURES:
        shap_val = shap_for_class.get(feat, 0.0)
        pct      = round(abs(shap_val) / total_abs_shap * 100, 2)
        contributions[feat] = {
            "sensor_value":   values.get(feat),
            "shap_value":     round(shap_val, 6),
            "importance_pct": pct,
            "direction":      "positive" if shap_val >= 0 else "negative",
            "interpretation": interpret_feature(feat, values.get(feat, 0.0)),
        }

    # Ranking fitur: paling berpengaruh ke paling kecil
    feature_ranking = sorted(
        contributions.items(),
        key=lambda x: x[1]["importance_pct"],
        reverse=True,
    )

    return {
        "predicted_class":    predicted_class,
        "contributions":      contributions,
        "feature_ranking":    [f[0] for f in feature_ranking],
        "all_classes_shap":   {
            cls: {feat: round(v, 6) for feat, v in feats.items()}
            for cls, feats in mean_shap.items()
        },
    }


async def fetch_firebase() -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(FIREBASE_URL)
        resp.raise_for_status()
        return resp.json()


# ── Schemas ───────────────────────────────────────────────────────────────────
class ManualInput(BaseModel):
    pH:  float
    DO:  float
    EC:  float
    TDS: float


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    """Cek status API dan PKL yang dimuat."""
    return {
        "status":      "healthy",
        "pkl_loaded":  True,
        "classes":     list(mean_shap.keys()),
        "features":    FEATURES,
    }


@app.get("/api/firebase/raw", tags=["Firebase"])
async def get_firebase_raw():
    """Ambil data mentah dari Firebase Realtime Database."""
    try:
        data = await fetch_firebase()
        return {"status": "ok", "data": data}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Firebase error: {e}")


@app.get("/api/analyze", tags=["SHAP Analysis"])
async def analyze_from_firebase():
    """
    Tarik data sensor terbaru dari Firebase, prediksi kelas kualitas air,
    lalu jalankan analisis SHAP untuk menjelaskan kontribusi setiap fitur.
    """
    try:
        raw = await fetch_firebase()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gagal mengambil data Firebase: {e}")

    # Parse fitur sensor
    sensor: Dict[str, Optional[float]] = {f: parse_float(raw.get(f)) for f in FEATURES}
    missing = [k for k, v in sensor.items() if v is None]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Fitur berikut tidak tersedia atau tidak valid di Firebase: {missing}",
        )

    values = {k: float(v) for k, v in sensor.items()}  # type: ignore

    # Gunakan label dari Firebase jika valid, fallback ke rule-based
    label_firebase = raw.get("Hasil")
    if label_firebase and label_firebase in mean_shap:
        predicted_class  = label_firebase
        prediction_source = "Firebase label (field: Hasil)"
    else:
        predicted_class  = classify_water(**values)
        prediction_source = "Rule-based classifier (fallback)"

    shap_result = compute_shap_analysis(values, predicted_class)

    return {
        "status":             "ok",
        "fetched_at":         datetime.utcnow().isoformat() + "Z",
        "device_id":          raw.get("device_id"),
        "received_at":        raw.get("received_at"),
        "rssi":               raw.get("rssi"),
        "snr":                raw.get("snr"),
        "sensor_values":      values,
        "predicted_class":    predicted_class,
        "prediction_source":  prediction_source,
        "shap_analysis":      shap_result,
    }


@app.post("/api/analyze/manual", tags=["SHAP Analysis"])
async def analyze_manual(body: ManualInput):
    """
    Input manual nilai sensor untuk analisis SHAP
    tanpa perlu mengambil data dari Firebase.
    """
    values = body.dict()
    predicted_class = classify_water(**values)
    shap_result     = compute_shap_analysis(values, predicted_class)

    return {
        "status":             "ok",
        "analyzed_at":        datetime.utcnow().isoformat() + "Z",
        "sensor_values":      values,
        "predicted_class":    predicted_class,
        "prediction_source":  "Rule-based classifier",
        "shap_analysis":      shap_result,
    }


@app.get("/api/shap/classes", tags=["SHAP Analysis"])
async def get_shap_classes():
    """
    Tampilkan seluruh mean SHAP values per kelas
    yang dimuat dari file mean_shap_per_class.pkl.
    """
    return {
        "status":              "ok",
        "classes":             list(mean_shap.keys()),
        "features":            FEATURES,
        "mean_shap_per_class": {
            cls: {feat: round(v, 6) for feat, v in feats.items()}
            for cls, feats in mean_shap.items()
        },
    }
