"""AttendAI Face Recognition — MediaPipe BlazeFace + OpenCV SFace Pipeline.

Detection : MediaPipe BlazeFace (primary) + YuNet (fallback)
Recognition: OpenCV SFace (128-d normalized embeddings)
Matching   : Cosine distance with configurable tolerance
"""
from __future__ import annotations

import logging
import urllib.request
from pathlib import Path
from threading import Lock

import cv2
import mediapipe as mp
import numpy as np

from app.core.config import settings

log = logging.getLogger(__name__)

# ── paths ──────────────────────────────────────────────────────────────────
_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "face"
_BLAZE_PATH = str(_MODEL_DIR / "blaze_face_short_range.tflite")
_YUNET_PATH = str(_MODEL_DIR / "face_detection_yunet_2023mar.onnx")
_SFACE_PATH = str(_MODEL_DIR / "face_recognition_sface_2021dec.onnx")

# ── tunables ───────────────────────────────────────────────────────────────
FACE_TOLERANCE = settings.FACE_TOLERANCE   # cosine distance threshold
MIN_DETECT_CONF = 0.45
MIN_FACE_PX = 20
MAX_IMAGE_SIDE = 2400
IOU_DEDUP = 0.40

# ── lazy singletons ───────────────────────────────────────────────────────
_mp_detector = None
_yunet = None
_recognizer = None
_lock = Lock()


def _ensure_models():
    """Ensure all required model files exist, downloading them if absent."""
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    models = [
        (
            _BLAZE_PATH,
            "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite",
        ),
        (
            _YUNET_PATH,
            "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        ),
        (
            _SFACE_PATH,
            "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        ),
    ]
    for path_str, url in models:
        p = Path(path_str)
        if not p.exists() or p.stat().st_size == 0:
            log.info("Downloading face model from %s -> %s", url, path_str)
            try:
                urllib.request.urlretrieve(url, path_str)
                log.info("Successfully downloaded %s", path_str)
            except Exception as e:
                log.error("Failed to download model %s: %s", path_str, e)


def _get_mp_detector():
    """Lazy-load MediaPipe BlazeFace detector."""
    global _mp_detector
    if _mp_detector is None:
        with _lock:
            if _mp_detector is None:
                _ensure_models()
                opts = mp.tasks.vision.FaceDetectorOptions(
                    base_options=mp.tasks.BaseOptions(
                        model_asset_path=_BLAZE_PATH,
                    ),
                    min_detection_confidence=MIN_DETECT_CONF,
                )
                _mp_detector = mp.tasks.vision.FaceDetector.create_from_options(opts)
    return _mp_detector


def _get_yunet():
    """Lazy-load YuNet detector as fallback."""
    global _yunet
    if _yunet is None:
        with _lock:
            if _yunet is None:
                _ensure_models()
                _yunet = cv2.FaceDetectorYN.create(
                    _YUNET_PATH, "", (320, 320), 0.5, 0.3, 5000,
                )
    return _yunet


def _get_recognizer():
    """Lazy-load SFace recognizer (128-d embeddings)."""
    global _recognizer
    if _recognizer is None:
        with _lock:
            if _recognizer is None:
                _ensure_models()
                _recognizer = cv2.FaceRecognizerSF.create(_SFACE_PATH, "")
    return _recognizer


# ── image helpers ─────────────────────────────────────────────────────────

def decode_image(data: bytes) -> np.ndarray:
    """Decode raw bytes -> BGR ndarray."""
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image")
    return image


def _resize(image: np.ndarray):
    h, w = image.shape[:2]
    longest = max(h, w)
    if longest <= MAX_IMAGE_SIDE:
        return image, 1.0
    s = MAX_IMAGE_SIDE / longest
    return cv2.resize(image, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), s


def _enhance(image: np.ndarray) -> np.ndarray:
    """CLAHE contrast enhancement."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


# ── detection ─────────────────────────────────────────────────────────────

def _iou(a, b):
    ax2, ay2 = a[0] + a[2], a[1] + a[3]
    bx2, by2 = b[0] + b[2], b[1] + b[3]
    ix = max(0, min(ax2, bx2) - max(a[0], b[0]))
    iy = max(0, min(ay2, by2) - max(a[1], b[1]))
    inter = ix * iy
    if inter == 0:
        return 0.0
    return inter / (a[2] * a[3] + b[2] * b[3] - inter + 1e-6)


def _nms_boxes(boxes: list[tuple]) -> list[tuple]:
    """Non-maximum suppression on (x, y, w, h, score) tuples."""
    if not boxes:
        return []
    boxes.sort(key=lambda b: -b[4])
    kept = []
    for b in boxes:
        if all(_iou(b, k) < IOU_DEDUP for k in kept):
            kept.append(b)
    return kept


def _detect_mediapipe(image: np.ndarray) -> list[tuple]:
    """Detect faces using MediaPipe BlazeFace.

    Returns list of (x, y, w, h, score) tuples in pixel coords.
    """
    h, w = image.shape[:2]
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    try:
        det = _get_mp_detector()
        result = det.detect(mp_image)
    except Exception as exc:
        log.warning("MediaPipe detection error: %s", exc)
        return []

    boxes = []
    for detection in result.detections:
        bb = detection.bounding_box
        x, y, bw, bh = bb.origin_x, bb.origin_y, bb.width, bb.height
        # clamp to image
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        bw = min(bw, w - x)
        bh = min(bh, h - y)
        if bw >= MIN_FACE_PX and bh >= MIN_FACE_PX:
            score = detection.categories[0].score if detection.categories else 0.5
            boxes.append((x, y, bw, bh, score))

    return boxes


def _detect_yunet(image: np.ndarray) -> list[tuple]:
    """Detect faces using YuNet as fallback.

    Returns list of (x, y, w, h, score) tuples.
    """
    det = _get_yunet()
    h, w = image.shape[:2]
    det.setInputSize((w, h))
    _, raw = det.detect(image)
    if raw is None:
        return []
    boxes = []
    for face in raw:
        x, y, fw, fh = face[:4].astype(int)
        score = float(face[14]) if len(face) > 14 else 0.5
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        fw = min(fw, w - x)
        fh = min(fh, h - y)
        if fw >= MIN_FACE_PX and fh >= MIN_FACE_PX:
            boxes.append((x, y, fw, fh, score))
    return boxes


def _build_yunet_face(image: np.ndarray, box: tuple) -> np.ndarray | None:
    """Run YuNet on a crop to get the 15-value face array needed by SFace."""
    x, y, w, h = box[:4]
    pad = int(max(w, h) * 0.3)
    px1 = max(0, x - pad)
    py1 = max(0, y - pad)
    ih, iw = image.shape[:2]
    px2 = min(iw, x + w + pad)
    py2 = min(ih, y + h + pad)
    crop = image[py1:py2, px1:px2]
    if crop.size == 0:
        return None

    det = _get_yunet()
    ch, cw = crop.shape[:2]
    det.setInputSize((cw, ch))
    _, raw = det.detect(crop)
    if raw is None or len(raw) == 0:
        return None

    # pick face closest to center
    cx, cy = cw / 2, ch / 2
    best = None
    best_dist = float("inf")
    for f in raw:
        fx, fy, fw, fh = f[:4]
        fcx, fcy = fx + fw / 2, fy + fh / 2
        d = (fcx - cx) ** 2 + (fcy - cy) ** 2
        if d < best_dist:
            best_dist = d
            best = f.copy()

    if best is not None:
        best[0] += px1
        best[1] += py1
        for i in range(4, 14, 2):
            best[i] += px1
            best[i + 1] += py1

    return best


def _detect_all(image: np.ndarray) -> list:
    """Hybrid detection: MediaPipe primary, YuNet secondary, merge + NMS."""
    processed, rs = _resize(image)
    enhanced = _enhance(processed)

    # Primary: MediaPipe on enhanced and original
    mp_boxes = _detect_mediapipe(enhanced)
    mp_boxes += _detect_mediapipe(processed)

    # Secondary: YuNet at multiple scales on enhanced
    yunet_boxes = _detect_yunet(enhanced)
    for scale in [1.4, 1.8]:
        scaled = cv2.resize(enhanced, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        for box in _detect_yunet(scaled):
            x, y, w, h, s = box
            yunet_boxes.append((x / scale, y / scale, w / scale, h / scale, s))

    # Merge all detections
    all_boxes = mp_boxes + yunet_boxes

    # Scale back to original image coords
    result = []
    oh, ow = image.shape[:2]
    for box in all_boxes:
        x, y, w, h, s = box
        x, y, w, h = x / rs, y / rs, w / rs, h / rs
        x = max(0, min(x, ow - 1))
        y = max(0, min(y, oh - 1))
        w = min(w, ow - x)
        h = min(h, oh - y)
        if w > 0 and h > 0:
            result.append((x, y, w, h, s))

    result = _nms_boxes(result)
    result.sort(key=lambda b: (b[1], b[0]))
    return result


# ── public API ─────────────────────────────────────────────────────────────

def detect_face_locations(image: np.ndarray) -> list[tuple]:
    """Detect all faces in image.

    Returns list of (top, right, bottom, left) tuples.
    """
    boxes = _detect_all(image)

    locations = []
    for (x, y, w, h, _) in boxes:
        x, y, w, h = int(x), int(y), int(w), int(h)
        locations.append((y, x + w, y + h, x))
    return locations


def extract_encodings(image: np.ndarray, locations: list[tuple], **_kwargs) -> list[np.ndarray]:
    """Extract 128-d SFace embeddings for each detected face location."""
    rec = _get_recognizer()
    boxes = _detect_all(image)
    encodings = []

    for i, box in enumerate(boxes):
        if i >= len(locations):
            break
        try:
            yunet_face = _build_yunet_face(image, box)
            if yunet_face is None:
                continue
            aligned = rec.alignCrop(image, yunet_face)
            feat = rec.feature(aligned).flatten().astype(np.float64)
            norm = np.linalg.norm(feat)
            if norm > 0:
                feat /= norm
            encodings.append(feat)
        except Exception as exc:
            log.debug("Encoding error for face %d: %s", i, exc)

    return encodings


def register_embedding(data: bytes):
    """Register a face from image bytes.

    Returns (embedding_list, image, location).
    """
    image = decode_image(data)
    boxes = _detect_all(image)
    if not boxes:
        raise ValueError(
            "No face detected. Move closer, improve lighting, and keep your full face visible."
        )

    # pick largest face
    box = max(boxes, key=lambda b: b[2] * b[3])
    x, y, w, h, _ = box
    location = (int(y), int(x + w), int(y + h), int(x))

    # get YuNet face for SFace alignment
    yunet_face = _build_yunet_face(image, box)
    if yunet_face is None:
        raise ValueError("Could not align face. Try another photo with better lighting.")

    rec = _get_recognizer()

    # generate from multiple image variants for robustness
    variants = [
        image,
        _enhance(image),
        cv2.convertScaleAbs(image, alpha=1.15, beta=12),
        cv2.convertScaleAbs(image, alpha=0.85, beta=-12),
    ]
    features = []
    for v in variants:
        try:
            aligned = rec.alignCrop(v, yunet_face)
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


def embedding_from_db(value) -> np.ndarray:
    """Convert DB-stored embedding to normalized float64 array."""
    arr = np.asarray(value, dtype=np.float64)
    if arr.size != 128:
        raise ValueError(f"Invalid embedding dimension: {arr.size}; expected 128")
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr /= norm
    return arr


def best_match(
    known_embeddings: list[tuple],
    face_encoding: np.ndarray,
) -> tuple:
    """Find closest match using cosine distance.

    Returns (student_id, distance, matched).
    """
    if not known_embeddings:
        return None, None, False

    ids = [sid for sid, _ in known_embeddings]
    matrix = np.asarray([emb for _, emb in known_embeddings], dtype=np.float64)
    query = face_encoding.reshape(1, -1).astype(np.float64)

    # normalize
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


def cosine_similarity(a, b) -> float:
    a = np.asarray(a, dtype=np.float64).reshape(-1)
    b = np.asarray(b, dtype=np.float64).reshape(-1)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0
