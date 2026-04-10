from pathlib import Path
from ultralytics import YOLO

DEFAULT_MODEL = "yolov8n.pt"
WEAPON_MODEL  = "best.pt"
MIN_SIZE_BYTES = 5120  # 5KB minimum


def load_models() -> dict:
    models = {}
    print(f"[YOLO] Loading general model: {DEFAULT_MODEL}")
    models["general"] = YOLO(DEFAULT_MODEL)
    if Path(WEAPON_MODEL).exists():
        print(f"[YOLO] Loading weapon model: {WEAPON_MODEL}")
        models["weapon"] = YOLO(WEAPON_MODEL)
    else:
        print(f"[YOLO] Weapon model not found, skipping.")
    return models


def run_detection(image_path: str, models: dict, confidence: float = 0.4) -> dict:
    image_path = Path(image_path)
    if not image_path.exists():
        return {"error": f"Image not found: {image_path}"}

    too_small = image_path.stat().st_size < MIN_SIZE_BYTES

    try:
        # Collect all detections from both models
        raw_detections = []

        general_model = models.get("general")
        if general_model:
            results = general_model(str(image_path), conf=confidence, verbose=False)
            for result in results:
                for box in result.boxes:
                    raw_detections.append({
                        "label": result.names[int(box.cls)],
                        "confidence": round(float(box.conf), 3),
                        "bbox": [round(float(x), 2) for x in box.xyxy[0].tolist()],
                        "source": "general"
                    })

        weapon_model = models.get("weapon")
        if weapon_model:
            results = weapon_model(str(image_path), conf=confidence, verbose=False)
            for result in results:
                for box in result.boxes:
                    raw_detections.append({
                        "label": result.names[int(box.cls)],
                        "confidence": round(float(box.conf), 3),
                        "bbox": [round(float(x), 2) for x in box.xyxy[0].tolist()],
                        "source": "weapon"
                    })

        # Group detections by unique labels for display
        label_summary = {}
        for det in raw_detections:
            label = det["label"]
            if label not in label_summary:
                label_summary[label] = {"label": label, "count": 0,
                                        "max_confidence": 0, "source": det["source"]}
            label_summary[label]["count"] += 1
            label_summary[label]["max_confidence"] = max(
                label_summary[label]["max_confidence"], det["confidence"])

        return {
            "file": image_path.name,
            "size_bytes": image_path.stat().st_size,
            "too_small": too_small,
            "detection_count": len(raw_detections),
            "label_summary": list(label_summary.values()),
            "detections": raw_detections
        }

    except Exception as e:
        return {"error": str(e)}


def scan_folder(folder_path: str, models: dict, confidence: float = 0.4) -> dict:
    """
    Runs dual detection on all images in folder.
    Returns dict with analysed results and skipped files list.
    """
    folder = Path(folder_path)
    supported = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    analysed = []
    skipped = []

    image_files = [f for f in folder.iterdir() if f.suffix.lower() in supported]

    if not image_files:
        return {"analysed": [], "skipped": [],
                "error": "No supported images found in folder"}

    for image_file in image_files:
        size = image_file.stat().st_size
        if size < MIN_SIZE_BYTES:
            skipped.append({
                "file": image_file.name,
                "size_bytes": size
            })
        else:
            result = run_detection(str(image_file), models, confidence)
            if result:
                analysed.append(result)

    return {"analysed": analysed, "skipped": skipped}