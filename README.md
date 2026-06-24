# Water Quality SHAP API

FastAPI service untuk analisis kualitas air menggunakan SHAP, dengan data sensor dari Firebase RTDB (LoRa).

---

## 📦 Struktur Project

```
watershap/
├── app/
│   └── main.py                  # FastAPI application
├── mean_shap_per_class.pkl      # SHAP model (mean per kelas)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
└── README.md
```

---

## 🚀 Menjalankan dengan Docker

```bash
# Build & jalankan
docker compose up --build -d

# Cek log
docker compose logs -f

# Stop
docker compose down
```

API akan berjalan di: **http://localhost:8000**

---

## 📡 Endpoints

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/health` | Status API & PKL |
| GET | `/api/firebase/raw` | Data mentah dari Firebase |
| GET | `/api/analyze` | Analisis SHAP dari data Firebase terbaru |
| POST | `/api/analyze/manual` | Analisis SHAP dengan input manual |
| GET | `/api/shap/classes` | Mean SHAP values per kelas dari PKL |
| GET | `/docs` | Swagger UI |
| GET | `/redoc` | ReDoc UI |

---

## 🧪 Contoh `POST /api/analyze/manual`

**Request:**
```json
{
  "pH": 8.34,
  "DO": 6.19,
  "EC": 0.59,
  "TDS": 292.5
}
```

**Response:**
```json
{
  "status": "ok",
  "predicted_class": "Baik",
  "shap_analysis": {
    "feature_ranking": ["pH", "EC", "DO", "TDS"],
    "contributions": {
      "pH": { "sensor_value": 8.34, "shap_value": 0.174679, "importance_pct": 32.4, "direction": "positive" },
      ...
    }
  }
}
```

---

## 🌊 Sumber Data Firebase

```
https://lora-tes-default-rtdb.asia-southeast1.firebasedatabase.app/faiz
```

Fitur yang digunakan: **pH, DO, EC, TDS**  
Label kelas: **Baik, Sedang, Buruk**

---

## 🐳 Menjalankan Lokal (tanpa Docker)

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
