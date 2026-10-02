"""AttendAI Face Recognition — YuNet + SFace Pipeline"""
from __future__ import annotations
import logging
from pathlib import Path
from threading import Lock
import cv2
import numpy as np
from app.core.config import settings

log = logging.getLogger(__name__)

_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "face"
_YUNET_PATH = str(_MODEL_DIR / "face_detection_yunet_2023mar.onnx")
_SFACE_PATH = str(_MODEL_DIR / "face_recognition_sface_2021dec.onnx")

FACE_TOLERANCE = settings.FACE_TOLERANCE
DETECT_SCORE = 0.55
NMS_THRESH = 0.30
MIN_FACE_PX = 20
MAX_IMAGE_SIDE = 2400
IOU_DEDUP = 0.40
_SCALES = [1.0, 1.5, 2.0]

_detector = None
_recognizer = None
_lock = Lock()
_face_cache: dict[int, list] = {}


def _get_detector():
    global _detector
    if _detector is None:
        with _lock:
            if _detector is None:
                _detector = cv2.FaceDetectorYN.create(
                    _YUNET_PATH, "", (320, 320), DETECT_SCORE, NMS_THRESH, 5000
                )
    return _detector


def _get_recognizer():
    global _recognizer
    if _recognizer is None:
        with _lock:
            if _recognizer is None:
                _recognizer = cv2.FaceRecognizerSF.create(_SFACE_PATH, "")
    return _recognizer


def decode_image(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image")
    return image


def _resize(image):
    h, w = image.shape[:2]
    longest = max(h, w)
    if longest <= MAX_IMAGE_SIDE:
        return image, 1.0
    s = MAX_IMAGE_SIDE / longest
    return cv2.resize(image, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), s


def _enhance(image):
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def _detect_at_scale(image, scale):
    det = _get_detector()
    if abs(scale - 1.0) > 0.01:
        scaled = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    else:
        scaled = image
    h, w = scaled.shape[:2]
    det.setInputSize((w, h))
    _, raw = det.detect(scaled)
    if raw is None:
        return []
    result = []
    for face in raw:
        f = face.copy()
        f[:14] /= scale
        if f[2] >= MIN_FACE_PX and f[3] >= MIN_FACE_PX:
            result.append(f)
    return result


def _iou(a, b):
    ax2, ay2 = a[0] + a[2], a[1] + a[3]
    bx2, by2 = b[0] + b[2], b[1] + b[3]
    ix = max(0, min(ax2, bx2) - max(a[0], b[0]))
    iy = max(0, min(ay2, by2) - max(a[1], b[1]))
    inter = ix * iy
    if inter == 0:
        return 0.0
    return inter / (a[2] * a[3] + b[2] * b[3] - inter + 1e-6)


def _nms(faces):
    if not faces:
        return []
    faces.sort(key=lambda f: -float(f[14]))
    kept = []
    for f in faces:
        if all(_iou(f, k) < IOU_DEDUP for k in kept):
            kept.append(f)
    return kept


def _detect_all(image):
    processed, rs = _resize(image)
    enhanced = _enhance(processed)
    all_faces = []
    for scale in _SCALES:
        all_faces.extend(_detect_at_scale(enhanced, scale))
    unique = _nms(all_faces)
    h, w = image.shape[:2]
    result = []
    for f in unique:
        f = f.copy()
        f[:14] /= rs
        f[0] = max(0, min(f[0], w - 1))
        f[1] = max(0, min(f[1], h - 1))
        f[2] = min(f[2], w - f[0])
        f[3] = min(f[3], h - f[1])
        if f[2] > 0 and f[3] > 0:
            result.append(f)
    result.sort(key=lambda f: (f[1], f[0]))
    return result


def detect_face_locations(image):
    faces = _detect_all(image)
    if len(_face_cache) > 30:
        for k in list(_face_cache.keys())[:-15]:
            _face_cache.pop(k, None)
    _face_cache[id(image)] = faces
    locations = []
    for f in faces:
        x, y, w, h = f[:4].astype(int)
        locations.append((y, x + w, y + h, x))
    return locations


def extract_encodings(image, locations, *, num_jitters=1):
    cached = _face_cache.pop(id(image), None)
    if cached is not None and len(cached) == len(locations):
        faces = cached
    else:
        faces = _detect_all(image)
    rec = _get_recognizer()
    encodings = []
    for face in faces:
        try:
            aligned = rec.alignCrop(image, face)
            feat = rec.feature(aligned).flatten().astype(np.float64)
            norm = np.linalg.norm(feat)
            if norm > 0:
                feat /= norm
            encodings.append(feat)
        except Exception:
            pass
    return encodings


def register_embedding(data):
    image = decode_image(data)
    faces = _detect_all(image)
    if not faces:
        raise ValueError("No face detected. Move closer, improve lighting, and keep your full face visible.")
    face = max(faces, key=lambda f: float(f[2] * f[3]))
    x, y, w, h = face[:4].astype(int)
    location = (y, x + w, y + h, x)
    rec = _get_recognizer()
    variants = [
        image,
        _enhance(image),
        cv2.convertScaleAbs(image, alpha=1.15, beta=12),
        cv2.convertScaleAbs(image, alpha=0.85, beta=-12),
    ]
    features = []
    for v in variants:
        try:
            aligned = rec.alignCrop(v, face)
            feat = rec.feature(aligned).flatten().astype(np.float64)
            features.append(feat)
        except Exception:
            pass
    if not features:
        raise ValueError("Could not generate face encoding. Try another clear photo.")
    avg = np.mean(features, axis=0)
    norm = np.linalg.norm(avg)
    if norm > 0:
        avg /= norm
    return avg.astype(np.float32).tolist(), image, location


def embedding_from_db(value):
    arr = np.asarray(value, dtype=np.float64)
    if arr.size != 128:
        raise ValueError(f"Invalid embedding dimension: {arr.size}; expected 128")
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr /= norm
    return arr


def best_match(known_embeddings, face_encoding):
    if not known_embeddings:
        return None, None, False
    ids = [sid for sid, _ in known_embeddings]
    matrix = np.asarray([emb for _, emb in known_embeddings], dtype=np.float64)
    query = face_encoding.reshape(1, -1).astype(np.float64)
    m_norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    m_norms[m_norms == 0] = 1.0
    matrix_n = matrix / m_norms
    q_norm = np.linalg.norm(query)
    query_n = query / q_norm if q_norm > 0 else query
    cos_sims = (matrix_n @ query_n.T).flatten()
    distances = 1.0 - cos_sims
    best_idx = int(np.argmin(distances))
    best_dist = float(distances[best_idx])
    best_id = ids[best_idx]
    matched = bool(best_dist <= FACE_TOLERANCE)
    return best_id, best_dist, matched


def cosine_similarity(a, b):
    a = np.asarray(a, dtype=np.float64).reshape(-1)
    b = np.asarray(b, dtype=np.float64).reshape(-1)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0
