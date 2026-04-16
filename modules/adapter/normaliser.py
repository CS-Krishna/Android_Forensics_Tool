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
    Handles Excel serial dates, proper header detection, and unnamed columns.
    """
    from datetime import datetime, timedelta
    raw_dir = Path(raw_dir)
    results = {}

    EXCEL_EPOCH = datetime(1899, 12, 30)

    def convert_excel_date(val):
        """Convert Excel serial date float to readable string."""
        try:
            dt = EXCEL_EPOCH + timedelta(days=float(val))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(val)

    def convert_cell(val):
        if val is None:
            return ""
        # pandas NaT / NaN
        try:
            if pd.isna(val):
                return ""
        except Exception:
            pass
        # Already a datetime object from pandas
        if hasattr(val, 'strftime'):
            return val.strftime("%Y-%m-%d %H:%M:%S")
        # Float that looks like an Excel serial date (1900–2100)
        if isinstance(val, float):
            if 20000.0 < val < 75000.0:
                return convert_excel_date(val)
            return str(val).rstrip('0').rstrip('.')
        if isinstance(val, int):
            if 20000 < val < 75000:
                return convert_excel_date(val)
            return str(val)
        return str(val).strip()

    for xlsx_file in raw_dir.rglob("*.xlsx"):
        name = xlsx_file.stem.replace(" ", "_").lower()
        try:
            # Read without auto date parsing so we get raw values
            df = pd.read_excel(
                xlsx_file,
                engine="openpyxl",
                header=0,
                dtype=object  # Keep everything as raw Python objects
            )

            # Drop fully empty columns
            df = df.dropna(axis=1, how="all")

            # Fix unnamed columns — if majority are unnamed, first row is the header
            unnamed = [c for c in df.columns if str(c).startswith("Unnamed")]
            if len(unnamed) > len(df.columns) // 2:
                df.columns = [str(v).strip() for v in df.iloc[0]]
                df = df[1:].reset_index(drop=True)

            # Clean column names
            df.columns = [str(c).strip() for c in df.columns]

            # Convert all cells
            records = []
            for _, row in df.iterrows():
                record = {}
                for col in df.columns:
                    record[col] = convert_cell(row[col])
                records.append(record)

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