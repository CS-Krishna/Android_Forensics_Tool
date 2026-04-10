import os
import json
import csv
import pandas as pd
from pathlib import Path



def find_aleapp_output(reports_path: str) -> dict:
    """
    Scans the ALEAPP output folder and collects all CSV artefact files.
    Returns a dict mapping artefact name -> list of row dicts.
    """
    artefacts = {}
    reports_dir = Path(reports_path)

    if not reports_dir.exists():
        raise FileNotFoundError(f"Reports path not found: {reports_path}")

    for csv_file in reports_dir.rglob("*.csv"):
        artefact_name = csv_file.stem  # filename without extension
        try:
            with open(csv_file, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                rows = [dict(row) for row in reader]
                if rows:
                    artefacts[artefact_name] = rows
        except Exception as e:
            artefacts[artefact_name] = {"error": str(e)}

    return artefacts


def normalise(reports_path: str, case_name: str = "case") -> dict:
    """
    Main normalisation function.
    Takes ALEAPP output path, returns a normalised JSON-serialisable dict.
    """
    raw = find_aleapp_output(reports_path)

    normalised = {
        "case": case_name,
        "artefact_count": len(raw),
        "artefacts": {}
    }

    for name, rows in raw.items():
        if isinstance(rows, list):
            normalised["artefacts"][name] = {
                "count": len(rows),
                "records": rows
            }
        else:
            normalised["artefacts"][name] = rows  # pass error through

    return normalised


def save_normalised(normalised: dict, output_path: str) -> str:
    """
    Saves the normalised dict as a JSON file.
    Returns the path to the saved file.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(normalised, f, indent=2, ensure_ascii=False)

    return str(out)

def parse_xlsx_messages(raw_dir: str) -> dict:
    """
    Finds SMS/MMS xlsx files exported by forensic tools and parses them.
    Returns a dict of artefact_name -> {count, records}
    """
    raw_dir = Path(raw_dir)
    results = {}

    for xlsx_file in raw_dir.rglob("*.xlsx"):
        name = xlsx_file.stem.replace(" ", "_").lower()
        try:
            df = pd.read_excel(xlsx_file, engine="openpyxl")
            records = df.fillna("").astype(str).to_dict(orient="records")
            results[name] = {
                "count": len(records),
                "records": records
            }
        except Exception as e:
            results[name] = {"error": str(e)}

    return results


def normalise_with_xlsx(reports_path: str, raw_dir: str, case_name: str = "case") -> dict:
    """
    Full normalisation — ALEAPP CSVs + xlsx message files.
    """
    normalised = normalise(reports_path, case_name)

    # Merge in xlsx artefacts
    xlsx_artefacts = parse_xlsx_messages(raw_dir)
    normalised["artefacts"].update(xlsx_artefacts)
    normalised["artefact_count"] = len(normalised["artefacts"])

    return normalised