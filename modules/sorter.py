import os
import re
import zipfile
import tarfile
import shutil
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tiff"}

INVALID_CHARS = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')


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