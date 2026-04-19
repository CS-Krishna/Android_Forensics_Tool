import os
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, send_file)

from modules.adapter.normaliser import normalise, save_normalised, normalise_with_xlsx
from modules.yolo.detector import load_models, scan_folder, run_detection
from modules.case_manager import (create_case, get_active_case, set_active_case,
                                   list_cases, get_case, init_cases_dir,
                                   load_registry, save_registry)
from modules.sorter import extract_input, sort_files
from modules.report_generator import generate_report

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 * 1024  # 50 GB
app.config['MAX_FORM_PARTS'] = 1000
app.config['MAX_FORM_MEMORY_SIZE'] = 50 * 1024 * 1024 * 1024

from werkzeug.exceptions import RequestEntityTooLarge

@app.errorhandler(RequestEntityTooLarge)
def handle_large_file(e):
    return jsonify({"error": "File too large for direct upload. Please use the path field instead — type the full path to your file (e.g. C:\\Users\\Test\\Downloads\\Android.zip) and click Ingest & Parse."}), 413

ALEAPP_PATH = "ALEAPP/aleapp.py"
init_cases_dir()
yolo_models = load_models()


# ── Helpers ───────────────────────────────────────────────

def case_path(case: dict, *parts) -> Path:
    return Path(case["path"]).joinpath(*parts)


def load_normalised(case: dict) -> dict:
    p = case_path(case, "normalised.json")
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


# ── Dashboard ─────────────────────────────────────────────

@app.route("/")
def dashboard():
    case = get_active_case()
    data = load_normalised(case) if case else {}
    return render_template("dashboard.html",
                           case=case,
                           all_cases=list_cases(),
                           artefact_count=data.get("artefact_count", 0))


# ── Case Management ───────────────────────────────────────

@app.route("/cases/new", methods=["POST"])
def new_case():
    name = request.form.get("name", "").strip()
    if not name:
        return redirect(url_for("dashboard"))
    create_case(name)
    return redirect(url_for("dashboard"))


@app.route("/cases/switch/<case_id>")
def switch_case(case_id):
    set_active_case(case_id)
    return redirect(url_for("dashboard"))


@app.route("/cases/delete/<case_id>", methods=["POST"])
def delete_case(case_id):
    registry = load_registry()
    if case_id not in registry["cases"]:
        return redirect(url_for("dashboard"))
    case = registry["cases"][case_id]
    case_dir = Path(case["path"])
    if case_dir.exists():
        shutil.rmtree(str(case_dir))
    del registry["cases"][case_id]
    if registry["active_case"] == case_id:
        remaining = list(registry["cases"].keys())
        registry["active_case"] = remaining[-1] if remaining else None
    save_registry(registry)
    return redirect(url_for("dashboard"))


@app.route("/cases/rename/<case_id>", methods=["POST"])
def rename_case(case_id):
    new_name = request.form.get("name", "").strip()
    if not new_name:
        return redirect(url_for("dashboard"))
    registry = load_registry()
    if case_id not in registry["cases"]:
        return redirect(url_for("dashboard"))
    registry["cases"][case_id]["name"] = new_name
    save_registry(registry)
    return redirect(url_for("dashboard"))


# ── Ingest ────────────────────────────────────────────────

@app.route("/ingest", methods=["POST"])
def ingest():
    case = get_active_case()
    if not case:
        return jsonify({"error": "No active case. Create a case first."}), 400

    raw_dir  = case_path(case, "raw")
    imgs_dir = case_path(case, "images")
    rpts_dir = case_path(case, "reports")

    try:
        # Handle uploaded file vs manually typed path
        uploaded_file = request.files.get("file")
        input_path = None

        if uploaded_file and uploaded_file.filename:
            tmp_dir = Path(tempfile.mkdtemp())
            tmp_path = tmp_dir / uploaded_file.filename
            uploaded_file.save(str(tmp_path))
            input_path = str(tmp_path)
        else:
            typed_path = request.form.get("input_path", "").strip()
            if not typed_path or not Path(typed_path).exists():
                return jsonify({"error": "Invalid input path. Enter a valid path or use Browse."}), 400
            input_path = typed_path

        # ── Pre-flight format check — fast, no extraction ──
        from modules.sorter import detect_proprietary_formats
        format_issues = detect_proprietary_formats(input_path)
        if format_issues:
            return jsonify({
                "error": "proprietary_format",
                "message": "Proprietary forensic format(s) detected.",
                "formats": format_issues
            }), 415

        # Compute SHA256 of evidence file
        import hashlib
        try:
            h = hashlib.sha256()
            with open(input_path, "rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
            evidence_hash = h.hexdigest()
            evidence_name = Path(input_path).name
            registry = load_registry()
            if case["id"] in registry["cases"]:
                registry["cases"][case["id"]]["evidence_hash"] = evidence_hash
                registry["cases"][case["id"]]["evidence_file"] = evidence_name
                save_registry(registry)
        except Exception as hash_err:
            print(f"[Ingest] Hash computation skipped: {hash_err}")

        # Extract
        result = extract_input(input_path, str(raw_dir))
        if isinstance(result, dict) and "error" in result:
            return jsonify(result), 400

        # Sort images
        sort_summary = sort_files(str(raw_dir), str(imgs_dir))

        # Run ALEAPP
        cmd = ["python", ALEAPP_PATH, "-t", "fs",
               "-i", str(raw_dir), "-o", str(rpts_dir)]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            return jsonify({"error": "ALEAPP timed out"}), 500

        # Normalise
        norm = normalise_with_xlsx(str(rpts_dir), str(raw_dir), case["name"])
        save_normalised(norm, str(case_path(case, "normalised.json")))

        return jsonify({
            "status": "success",
            "images_sorted": sort_summary["images_sorted"],
            "artefacts_parsed": norm["artefact_count"]
        })

    except Exception as e:
        import traceback
        print(f"[Ingest] Error: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

    @app.route("/case-hash-pdf/<case_id>")
    def serve_hash_pdf(case_id):
        case = get_case(case_id)
        if not case:
            return "Case not found", 404
        raw_dir = Path(case["path"]) / "raw"
        for f in raw_dir.rglob("*"):
            if not f.is_file():
                continue
            if "hash" in f.name.lower() and f.suffix.lower() == ".pdf":
                return send_file(
                    str(f.resolve()),
                    mimetype="application/pdf",
                    as_attachment=False,
                    download_name=f.name
                )
        return "No hash PDF found", 404

    # Sort images
    sort_summary = sort_files(str(raw_dir), str(imgs_dir))

    # Run ALEAPP
    cmd = ["python", ALEAPP_PATH, "-t", "fs",
           "-i", str(raw_dir), "-o", str(rpts_dir)]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "ALEAPP timed out"}), 500

    # Normalise
    norm = normalise_with_xlsx(str(rpts_dir), str(raw_dir), case["name"])
    save_normalised(norm, str(case_path(case, "normalised.json")))

    return jsonify({
        "status": "success",
        "images_sorted": sort_summary["images_sorted"],
        "artefacts_parsed": norm["artefact_count"]
    })


# ── YOLOv8 ────────────────────────────────────────────────

@app.route("/run_yolo", methods=["POST"])
def run_yolo():
    case = get_active_case()
    if not case:
        return jsonify({"error": "No active case"}), 400
    imgs_dir = case_path(case, "images")
    try:
        results = scan_folder(str(imgs_dir), yolo_models)
        out = case_path(case, "yolo_results.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        # Check if request came from images page or dashboard
        referrer = request.referrer or ""
        if "/images" in referrer:
            return redirect(url_for("image_analysis"))
        return jsonify({
            "status": "success",
            "images_analysed": len(results.get("analysed", [])),
            "images_skipped": len(results.get("skipped", []))
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/run_yolo_small", methods=["POST"])
def run_yolo_small():
    case = get_active_case()
    if not case:
        return jsonify({"error": "No active case"}), 400
    imgs_dir = case_path(case, "images")
    results_path = case_path(case, "yolo_results.json")
    try:
        existing = {"analysed": [], "skipped": []}
        if results_path.exists():
            with open(results_path, encoding="utf-8") as f:
                existing = json.load(f)
        newly_analysed = []
        for item in existing.get("skipped", []):
            img_path = imgs_dir / item["file"]
            result = run_detection(str(img_path), yolo_models)
            if result:
                newly_analysed.append(result)
        existing["analysed"].extend(newly_analysed)
        existing["skipped"] = []
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
        return redirect(url_for("image_analysis"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Artefacts ─────────────────────────────────────────────

@app.route("/artefacts")
def artefacts():
    case = get_active_case()
    data = load_normalised(case) if case else {}
    return render_template("artefacts.html",
                           case=case,
                           artefacts=data.get("artefacts", {}))


@app.route("/artefacts/<name>")
def artefact_detail(name):
    case = get_active_case()
    data = load_normalised(case) if case else {}
    artefact = data.get("artefacts", {}).get(name, {})
    query = request.args.get("q", "").strip().lower()
    page = int(request.args.get("page", 1))
    per_page = 50

    # Strip bare # and Unnamed index columns from display
    for art_name, art_content in [( name, artefact )]:
        if "records" in art_content:
            art_content["records"] = [
                {k: v for k, v in r.items()
                 if k.strip() not in ("#", "Unnamed: 0")}
                for r in art_content["records"]
            ]

    all_records = artefact.get("records", [])
    if query:
        all_records = [r for r in all_records
                       if any(query in str(v).lower() for v in r.values())]

    total = len(all_records)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = min(start + per_page, total)

    return render_template("artefact_detail.html", case=case,
                           name=name, records=all_records[start:end],
                           query=query, page=page,
                           total=total, total_pages=total_pages,
                           start=start, end=end)


# ── SMS Search ────────────────────────────────────────────

@app.route("/sms")
def sms_search():
    from modules.report_generator import extract_hash_values, build_timeline
    case = get_active_case()
    data = load_normalised(case) if case else {}
    query = request.args.get("q", "").strip()
    active_tab = request.args.get("tab", "sms")
    page = int(request.args.get("page", 1))
    tl_from_date = request.args.get("tl_from_date", "").strip()
    tl_from_time = request.args.get("tl_from_time", "").strip()
    tl_to_date   = request.args.get("tl_to_date", "").strip()
    tl_to_time   = request.args.get("tl_to_time", "").strip()
    per_page = 50

    # ← THIS must be here before anything else
    all_results = []

    # Build combined filter strings
    tl_from = ""
    tl_to   = ""
    if tl_from_date:
        tl_from = tl_from_date + (" " + tl_from_time if tl_from_time else " 00:00")
    if tl_to_date:
        tl_to = tl_to_date + (" " + tl_to_time if tl_to_time else " 23:59")

    # Timeline and hashes
    timeline = []
    hashes = []
    if case:
        raw_timeline = build_timeline(data.get("artefacts", {}))
        filtered = raw_timeline
        if tl_from:
            filtered = [e for e in filtered if e["date"] >= tl_from]
        if tl_to:
            filtered = [e for e in filtered if e["date"] <= tl_to]
        timeline = filtered
        hashes = extract_hash_values(case_path(case, "raw"))

    # SMS search logic
    query_lower = query.lower()
    serial_search = None
    if query.startswith("#") and query[1:].strip().isdigit():
        serial_search = int(query[1:].strip())

    sms_keywords = ["sms", "message", "mms", "chat", "whatsapp"]
    record_counter = {}

    for name, content in data.get("artefacts", {}).items():
        if any(kw in name.lower() for kw in sms_keywords):
            if name not in record_counter:
                record_counter[name] = 0
            for record in content.get("records", []):
                record_counter[name] += 1
                serial = record_counter[name]
                clean_record = {k: v for k, v in record.items()
                                if k.strip() not in ("#", "Unnamed: 0")}

                if serial_search is not None:
                    if serial == serial_search:
                        all_results.append({"artefact": name,
                                            "serial": serial,
                                            "record": clean_record})
                elif query_lower:
                    if any(query_lower in str(v).lower()
                           for v in record.values()):
                        all_results.append({"artefact": name,
                                            "serial": serial,
                                            "record": clean_record})
                else:
                    all_results.append({"artefact": name,
                                        "serial": serial,
                                        "record": clean_record})

    total = len(all_results)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = min(start + per_page, total)

    return render_template("sms.html", case=case,
                           results=all_results[start:end],
                           query=query, page=page,
                           total=total, total_pages=total_pages,
                           start=start, end=end,
                           active_tab=active_tab,
                           timeline=timeline,
                           tl_from=tl_from, tl_to=tl_to,
                           tl_from_date=tl_from_date,
                           tl_from_time=tl_from_time,
                           tl_to_date=tl_to_date,
                           tl_to_time=tl_to_time,
                           hashes=hashes)


# ── Image Analysis ────────────────────────────────────────

@app.route("/images")
def image_analysis():
    case = get_active_case()
    query = request.args.get("q", "").strip().lower()
    active_tag = request.args.get("tag", "").strip()
    show_small = request.args.get("show_small", "0") == "1"
    view_mode = request.args.get("view", "details")
    analysed = []
    skipped = []
    all_tags = []
    total_images = 0
    not_yet_analysed = False

    if case:
        results_path = case_path(case, "yolo_results.json")
        images_dir = case_path(case, "images")

        if not results_path.exists():
            # Check if there are images waiting to be analysed
            supported = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
            try:
                image_count = len([f for f in images_dir.iterdir()
                                   if f.suffix.lower() in supported])
            except Exception:
                image_count = 0
            not_yet_analysed = True
            return render_template("images.html", case=case,
                                   not_yet_analysed=True,
                                   pending_images=image_count,
                                   results=[], skipped=[],
                                   query=query, active_tag=active_tag,
                                   show_small=show_small,
                                   view_mode=view_mode,
                                   all_tags=[], total_images=0,
                                   min_size_kb=5)

        with open(results_path, encoding="utf-8") as f:
            data = json.load(f)
        analysed = data.get("analysed", [])
        skipped = data.get("skipped", [])
        total_images = len(analysed)

        # Build tag summary
        tag_counts = {}
        for img in analysed:
            for det in img.get("label_summary", []):
                label = det["label"]
                if label not in tag_counts:
                    tag_counts[label] = {"label": label, "count": 0,
                                         "source": det["source"]}
                tag_counts[label]["count"] += 1
        all_tags = sorted(tag_counts.values(),
                          key=lambda x: (0 if x["source"] == "weapon" else 1,
                                         x["label"]))

        if active_tag:
            analysed = [r for r in analysed
                        if any(d["label"] == active_tag
                               for d in r.get("label_summary", []))]
        elif query:
            analysed = [r for r in analysed
                        if any(query in d["label"].lower()
                               for d in r.get("label_summary", []))]

    return render_template("images.html", case=case,
                           not_yet_analysed=False,
                           pending_images=0,
                           results=analysed, skipped=skipped,
                           query=query, active_tag=active_tag,
                           show_small=show_small, view_mode=view_mode,
                           all_tags=all_tags, total_images=total_images,
                           min_size_kb=5)


# ── Image Serve ───────────────────────────────────────────

@app.route("/case-image/<case_id>/<filename>")
def serve_image(case_id, filename):
    case = get_case(case_id)
    if not case:
        return "Case not found", 404
    img_path = Path(case["path"]) / "images" / filename
    if not img_path.exists():
        return "Image not found", 404
    return send_file(str(img_path))

@app.route("/export-report", methods=["GET", "POST"])
def export_report():
    case = get_active_case()
    if not case:
        return "No active case", 400

    investigator = request.args.get("investigator", "N/A").strip()
    data = load_normalised(case)
    yolo_path = case_path(case, "yolo_results.json")
    images_dir = case_path(case, "images")

    html = generate_report(case, data, yolo_path, images_dir, investigator)

    from flask import Response
    filename = f"forensic_report_{case['id']}.html"
    return Response(html, mimetype="text/html",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)