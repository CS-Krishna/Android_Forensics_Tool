from pathlib import Path
from ultralytics import YOLO

DEFAULT_MODEL = "yolo11m.pt"
WEAPON_MODEL  = "best.pt"
MIN_SIZE_BYTES = 5120  # 5KB


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


def run_detection(image_path: str, models: dict,
                  confidence: float = 0.4,
                  force: bool = False) -> dict:
    """
    Runs both models on a single image.
    force=True bypasses the 5KB size filter.
    Always returns a dict with size_bytes field.
    """
    image_path = Path(image_path)

    if not image_path.exists():
        return {
            "file": image_path.name,
            "size_bytes": 0,
            "too_small": False,
            "detection_count": 0,
            "label_summary": [],
            "detections": [],
            "error": f"Image not found: {image_path}"
        }

    size = image_path.stat().st_size

    base = {
        "file": image_path.name,
        "size_bytes": size,
        "too_small": size < MIN_SIZE_BYTES,
        "detection_count": 0,
        "label_summary": [],
        "detections": []
    }

    try:
        raw_detections = []

        general = models.get("general")
        if general:
            for result in general(str(image_path), conf=confidence, verbose=False):
                for box in result.boxes:
                    raw_detections.append({
                        "label": result.names[int(box.cls)],
                        "confidence": round(float(box.conf), 3),
                        "bbox": [round(float(x), 2) for x in box.xyxy[0].tolist()],
                        "source": "general"
                    })

        weapon = models.get("weapon")
        if weapon:
            for result in weapon(str(image_path), conf=0.85, verbose=False):
                for box in result.boxes:
                    raw_detections.append({
                        "label": result.names[int(box.cls)],
                        "confidence": round(float(box.conf), 3),
                        "bbox": [round(float(x), 2) for x in box.xyxy[0].tolist()],
                        "source": "weapon"
                    })

        # Group by label
        label_summary = {}
        for det in raw_detections:
            label = det["label"]
            if label not in label_summary:
                label_summary[label] = {
                    "label": label,
                    "count": 0,
                    "max_confidence": 0,
                    "source": det["source"]
                }
            label_summary[label]["count"] += 1
            label_summary[label]["max_confidence"] = max(
                label_summary[label]["max_confidence"], det["confidence"])

        base["detection_count"] = len(raw_detections)
        base["label_summary"] = list(label_summary.values())
        base["detections"] = raw_detections
        return base

    except Exception as e:
        base["error"] = str(e)
        return base


def scan_folder(folder_path: str, models: dict,
                confidence: float = 0.4) -> dict:
    """
    Runs dual detection on all images in folder.
    Returns {"analysed": [...], "skipped": [...]}
    """
    folder = Path(folder_path)
    supported = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    analysed = []
    skipped = []

    try:
        image_files = [f for f in folder.iterdir()
                       if f.suffix.lower() in supported]
    except Exception:
        return {"analysed": [], "skipped": [],
                "error": "Could not read images folder"}

    if not image_files:
        return {"analysed": [], "skipped": []}

    for image_file in image_files:
        size = image_file.stat().st_size
        if size < MIN_SIZE_BYTES:
            skipped.append({
                "file": image_file.name,
                "size_bytes": size
            })
        else:
            result = run_detection(str(image_file), models, confidence)
            analysed.append(result)

    return {"analysed": analysed, "skipped": skipped}