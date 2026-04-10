import json
import os
from pathlib import Path
from datetime import datetime

CASES_DIR = Path("cases")
CASES_REGISTRY = CASES_DIR / "cases.json"


def init_cases_dir():
    CASES_DIR.mkdir(exist_ok=True)
    if not CASES_REGISTRY.exists():
        with open(CASES_REGISTRY, "w") as f:
            json.dump({"active_case": None, "cases": {}}, f, indent=2)


def load_registry() -> dict:
    init_cases_dir()
    with open(CASES_REGISTRY, encoding="utf-8") as f:
        return json.load(f)


def save_registry(registry: dict):
    with open(CASES_REGISTRY, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)


def create_case(name: str) -> dict:
    registry = load_registry()
    case_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    case_path = CASES_DIR / case_id

    # Create all subfolders
    (case_path / "raw").mkdir(parents=True, exist_ok=True)
    (case_path / "images").mkdir(exist_ok=True)
    (case_path / "reports").mkdir(exist_ok=True)

    case = {
        "id": case_id,
        "name": name,
        "created": datetime.now().isoformat(),
        "path": str(case_path)
    }

    registry["cases"][case_id] = case
    registry["active_case"] = case_id
    save_registry(registry)
    return case


def get_active_case() -> dict | None:
    registry = load_registry()
    active_id = registry.get("active_case")
    if not active_id:
        return None
    return registry["cases"].get(active_id)


def set_active_case(case_id: str) -> dict | None:
    registry = load_registry()
    if case_id not in registry["cases"]:
        return None
    registry["active_case"] = case_id
    save_registry(registry)
    return registry["cases"][case_id]


def list_cases() -> list:
    registry = load_registry()
    return list(registry["cases"].values())


def get_case(case_id: str) -> dict | None:
    registry = load_registry()
    return registry["cases"].get(case_id)