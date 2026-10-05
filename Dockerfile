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

# Download face models if not present
RUN mkdir -p models/face && \
    curl -fsSL -o models/face/blaze_face_short_range.tflite \
    https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite && \
    curl -fsSL -o models/face/face_detection_yunet_2023mar.onnx \
    https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx && \
    curl -fsSL -o models/face/face_recognition_sface_2021dec.onnx \
    https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
