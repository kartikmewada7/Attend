# ==========================================
# STAGE 1: Build Frontend (Vite/React)
# ==========================================
FROM node:18 AS frontend-builder
WORKDIR /app/frontend

# Frontend dependencies install karein
COPY attendAI-frontend/package*.json ./
RUN npm install

# Frontend code copy karke build karein (assuming 'dist' folder banta hai)
COPY attendAI-frontend/ ./
RUN npm run build 


# ==========================================
# STAGE 2: Setup Python Backend & Add Frontend
# ==========================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

# System dependencies for OpenCV & MediaPipe (no dlib/cmake needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Backend code copy karein
COPY app ./app
COPY scripts ./scripts

# STAGE 1 se frontend ke build files utha kar backend ke 'static' folder mein daalein
COPY --from=frontend-builder /app/frontend/dist ./app/static

# Copy models directory if present locally, otherwise download from Hugging Face CDN
COPY models ./models
RUN mkdir -p models/face && \
    ([ -f models/face/blaze_face_short_range.tflite ] || curl -fsSL -o models/face/blaze_face_short_range.tflite https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite) && \
    ([ -f models/face/face_detection_yunet_2023mar.onnx ] || curl -fsSL -o models/face/face_detection_yunet_2023mar.onnx https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx) && \
    ([ -f models/face/face_recognition_sface_2021dec.onnx ] || curl -fsSL -o models/face/face_recognition_sface_2021dec.onnx https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx)

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
