# Smart Attendance System

**FaceNet + Haar Cascade + Cosine Similarity — No Classifiers**

---

## Architecture Overview

```
Smart_Attendance_System/
│
├── registered_faces/          ← Optional: saved face crop images (for inspection)
│   └── <Person_Name>/
│       └── photo_face_0.jpg
│
├── embeddings/                ← Core: persisted FaceNet embeddings
│   ├── face_embeddings.pkl    ← np.ndarray  shape (N, 512)
│   ├── labels.pkl             ← List[str]   length N  (parallel to embeddings)
│   └── metadata.json          ← Registration timestamps + counts
│
├── attendance/                ← Daily attendance CSV files
│   └── attendance_YYYY-MM-DD.csv
│
├── database/                  ← SQLite for queries + reports
│   └── attendance.db
│
├── utils/
│   ├── __init__.py
│   ├── config.py              ← All constants in one place
│   ├── logger.py              ← Coloured rotating-file logger
│   ├── face_detector.py       ← Haar Cascade face detection + cropping
│   ├── embedding_generator.py ← FaceNet (InceptionResnetV1) embeddings
│   ├── embedding_store.py     ← Pickle-based CRUD for embedding database
│   └── similarity.py          ← Cosine similarity recognition engine
│
├── register_face.py           ← Register new person (offline)
├── attendance_system.py       ← Live webcam recognition + marking
├── attendance_manager.py      ← Query + export attendance records
├── requirements.txt
└── README.md
```

---

## How It Works

### Recognition Pipeline (No Classifier)

```
Face Image (160×160 RGB)
        │
        ▼
InceptionResnetV1 (FaceNet)
        │
        ▼
512-D L2-normalised embedding vector
        │
        ▼
cosine_similarity(query, each_reference_embedding)
        │
        ├── max_score >= 0.75  →  Person RECOGNISED
        └── max_score <  0.75  →  UNKNOWN
```

**Why cosine similarity instead of a classifier?**

- FaceNet is trained with a triplet loss / contrastive loss that makes same-person embeddings cluster together and different-person embeddings spread apart.
- Cosine similarity directly measures the angle between two embedding vectors — a perfect match = 1.0, completely different = 0.0 (or negative).
- No training data needed beyond the registered face images.
- Adding/removing a person never requires re-training anything.

---

## Installation

```bash
git clone <repo>
cd Smart_Attendance_System
pip install -r requirements.txt
```

**Python:** 3.8 – 3.10 recommended  
**GPU:** Automatically used if CUDA is available (falls back to CPU)

---

## Quick Start

### 1. Register a person

```bash
# Single image
python register_face.py --name "Alice Smith" --images alice.jpg

# Multiple images (recommended: 5–10 for best accuracy)
python register_face.py --name "Bob Jones" --images bob1.jpg bob2.jpg bob3.jpg

# Glob pattern
python register_face.py --name "Charlie" --images "photos/charlie/*.jpg"

# Interactive mode
python register_face.py
```

### 2. Start live attendance

```bash
python attendance_system.py

# Custom camera or threshold
python attendance_system.py --camera 1 --threshold 0.78
```

### 3. View / export attendance

```bash
python attendance_manager.py --today
python attendance_manager.py --date 2024-06-12
python attendance_manager.py --person "Alice Smith"
python attendance_manager.py --summary
python attendance_manager.py --export-excel
```

---

## Configuration

Edit `utils/config.py`:

| Constant | Default | Description |
|---|---|---|
| `COSINE_THRESHOLD` | `0.75` | Min similarity to accept a match |
| `HAAR_SCALE_FACTOR` | `1.1` | Detection sensitivity |
| `HAAR_MIN_NEIGHBORS` | `5` | False-positive filter |
| `ATTENDANCE_COOLDOWN_SECONDS` | `30` | Re-marking cooldown |
| `FACENET_PRETRAINED` | `vggface2` | Pre-trained weights |
| `WEBCAM_INDEX` | `0` | Camera device index |

---

## Tuning the Threshold

| Threshold | Effect |
|---|---|
| 0.60 | Very permissive — fewer false rejections, more false acceptances |
| 0.75 | **Recommended default** — balanced accuracy |
| 0.85 | Very strict — fewer false acceptances, more false rejections |

---

## Tips for Best Accuracy

1. **Register 5–10 images per person** with varied lighting and angles.
2. Use clear, frontal, well-lit photos at registration time.
3. Avoid extreme glasses, hats, or masks at registration (or register with them).
4. Higher cosine threshold → more secure but stricter.
5. Use `--save-crops` when registering to visually verify detected crops.
