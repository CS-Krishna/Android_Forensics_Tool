import os
import re
import zipfile
import tarfile
import shutil
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tiff"}

INVALID_CHARS = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')

PROPRIETARY_FORMATS = {
    ".xry": {
        "tool": "XAMN / XACT (MSAB)",
        "instruction": "Open the .xrycase file in XAMN or XACT, go to File → Export → Logical Export, export as a folder or ZIP, then re-ingest the exported folder."
    },
    ".xrycase": {
        "tool": "XAMN / XACT (MSAB)",
        "instruction": "Open this .xrycase file in XAMN or XACT, go to File → Export → Logical Export, export as a folder or ZIP, then re-ingest the exported folder."
    },
    ".e01": {
        "tool": "FTK Imager or Autopsy",
        "instruction": "Open the .e01 image in FTK Imager, go to File → Export Logical Image, export as a folder or ZIP, then re-ingest the exported folder."
    },
    ".ex01": {
        "tool": "FTK Imager or Autopsy",
        "instruction": "Open the .ex01 image in FTK Imager, go to File → Export Logical Image, export as a folder or ZIP, then re-ingest the exported folder."
    },
    ".aff": {
        "tool": "Autopsy or Guymager",
        "instruction": "Open the .aff image in Autopsy, export the filesystem as a logical folder, then re-ingest that folder."
    },
    ".aff4": {
        "tool": "Autopsy or AFC4 tools",
        "instruction": "Open the .aff4 image in Autopsy, export the filesystem as a logical folder, then re-ingest that folder."
    },
    ".dd": {
        "tool": "FTK Imager or Autopsy",
        "instruction": "Open the .dd raw image in FTK Imager or Autopsy, export the filesystem as a logical folder, then re-ingest that folder."
    },
    ".img": {
        "tool": "FTK Imager or Autopsy",
        "instruction": "Open the .img raw image in FTK Imager or Autopsy, export the filesystem as a logical folder, then re-ingest that folder."
    },
    ".bin": {
        "tool": "FTK Imager or XACT",
        "instruction": "This appears to be a raw binary image. Open it in FTK Imager or the originating acquisition tool, export the filesystem as a logical folder, then re-ingest that folder."
    },
    ".cellebrite": {
        "tool": "Cellebrite UFED Physical Analyzer",
        "instruction": "Open this file in Cellebrite UFED Physical Analyzer, export as a logical folder or ZIP, then re-ingest the exported folder."
    },
    ".ufd": {
        "tool": "Cellebrite UFED Physical Analyzer",
        "instruction": "Open this .ufd file in Cellebrite UFED Physical Analyzer, go to Export → File System Export, then re-ingest the exported folder."
    },
    ".ofb": {
        "tool": "Oxygen Forensic Detective",
        "instruction": "Open this .ofb file in Oxygen Forensic Detective, go to File → Export → Export to Folder, then re-ingest the exported folder."
    },
    ".oxs": {
        "tool": "Oxygen Forensic Detective",
        "instruction": "Open this .oxs file in Oxygen Forensic Detective, go to File → Export → Export to Folder, then re-ingest the exported folder."
    },
}


def detect_proprietary_formats(input_path: str) -> list:
    """
    Fast pre-flight check for proprietary forensic formats.
    Checks the input file itself first, then scans archive contents
    using header/index only — never extracts anything.
    Returns a list of detected format issues.
    """
    input_path = Path(input_path)
    detected = []
    seen_suffixes = set()

    def add_detection(filename, suffix):
        if suffix not in seen_suffixes:
            seen_suffixes.add(suffix)
            detected.append({
                "file": filename,
                "suffix": suffix,
                **PROPRIETARY_FORMATS[suffix]
            })

    # Check the input file itself first — instant
    suffix = input_path.suffix.lower()
    if suffix in PROPRIETARY_FORMATS:
        add_detection(input_path.name, suffix)
        return detected  # No need to look inside

    # For zip — read central directory only (no extraction, very fast even for large files)
    if suffix == ".zip":
        try:
            import zipfile
            with zipfile.ZipFile(input_path, "r") as z:
                # namelist() only reads the central directory header — not the file data
                for name in z.namelist():
                    ext = Path(name).suffix.lower()
                    if ext in PROPRIETARY_FORMATS:
                        add_detection(name, ext)
        except Exception:
            pass

    # For tar/gz — read member list only (no extraction)
    elif suffix in {".tar", ".gz", ".tgz"} or str(input_path).endswith(".tar.gz"):
        try:
            import tarfile
            with tarfile.open(input_path, "r:*") as t:
                # getmembers() reads the tar index — not the file data
                for member in t.getmembers():
                    ext = Path(member.name).suffix.lower()
                    if ext in PROPRIETARY_FORMATS:
                        add_detection(member.name, ext)
        except Exception:
            pass

    # For folder — scan filenames only, no reading
    elif input_path.is_dir():
        try:
            for f in input_path.rglob("*"):
                if f.is_file():
                    ext = f.suffix.lower()
                    if ext in PROPRIETARY_FORMATS:
                        add_detection(f.name, ext)
        except Exception:
            pass

    return detected


def sanitise_path(name: str) -> str:
    """Strips carriage returns and invalid Windows filename characters."""
    name = name.replace("\r", "").replace("\n", "")
    parts = Path(name).parts
    clean_parts = []
    for part in parts:
        part = INVALID_CHARS.sub("_", part)
        part = part.strip(". ")
        if not part:
            part = "_"
        clean_parts.append(part)
    return str(Path(*clean_parts)) if clean_parts else "_"


def extract_input(input_path: str, raw_dir: str) -> str:
    """
    Extracts zip/tar/gz into raw_dir, or copies folder contents.
    Sanitises filenames for Windows compatibility.
    Returns the path to the extracted content.
    """
    input_path = Path(input_path)
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    suffix = input_path.suffix.lower()

    if suffix == ".zip":
        with zipfile.ZipFile(input_path, "r") as z:
            for member in z.infolist():
                clean_name = sanitise_path(member.filename)
                target = raw_dir / clean_name
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)

    elif suffix in {".tar", ".gz", ".tgz"} or input_path.name.endswith(".tar.gz"):
        with tarfile.open(input_path, "r:*") as t:
            for member in t.getmembers():
                clean_name = sanitise_path(member.name)
                target = raw_dir / clean_name
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        f = t.extractfile(member)
                        if f:
                            with open(target, "wb") as dst:
                                shutil.copyfileobj(f, dst)
                    except Exception:
                        pass  # Skip unreadable files

    elif input_path.is_dir():
        shutil.copytree(str(input_path), str(raw_dir), dirs_exist_ok=True)

    else:
        return {"error": f"Unsupported format: {suffix}. Please export as zip, tar, or folder from FTK Imager / Oxygen Forensic."}

    # Handle nested tar/zip files (e.g. Google Pixel 3.tar inside android_9.tar.gz)
    for nested in raw_dir.rglob("*.tar"):
        nested_out = nested.parent / nested.stem
        if not nested_out.exists():
            print(f"[Sorter] Extracting nested tar: {nested.name}")
            nested_out.mkdir(parents=True, exist_ok=True)
            try:
                with tarfile.open(nested, "r:*") as t:
                    for member in t.getmembers():
                        clean_name = sanitise_path(member.name)
                        target = nested_out / clean_name
                        if member.isdir():
                            target.mkdir(parents=True, exist_ok=True)
                        elif member.isfile():
                            target.parent.mkdir(parents=True, exist_ok=True)
                            try:
                                f = t.extractfile(member)
                                if f:
                                    with open(target, "wb") as dst:
                                        shutil.copyfileobj(f, dst)
                            except Exception:
                                pass
            except Exception as e:
                print(f"[Sorter] Could not extract {nested.name}: {e}")

    return str(raw_dir)


def sort_files(raw_dir: str, images_dir: str) -> dict:
    """
    Walks raw_dir and sorts image files into images_dir.
    Returns a summary of what was sorted.
    """
    raw_dir = Path(raw_dir)
    images_dir = Path(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)

    images_found = 0
    other_files = 0

    for file in raw_dir.rglob("*"):
        if file.is_file():
            if file.suffix.lower() in IMAGE_EXTENSIONS:
                dest = images_dir / file.name
                counter = 1
                while dest.exists():
                    dest = images_dir / f"{file.stem}_{counter}{file.suffix}"
                    counter += 1
                shutil.copy2(str(file), str(dest))
                images_found += 1
            else:
                other_files += 1

    return {
        "images_sorted": images_found,
        "other_files": other_files,
        "raw_dir": str(raw_dir),
        "images_dir": str(images_dir)
    }