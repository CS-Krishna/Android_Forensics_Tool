import json
import base64
from pathlib import Path
from datetime import datetime


def encode_image(img_path: Path) -> str | None:
    """Encode image to base64 data URI."""
    try:
        suffix = img_path.suffix.lower()
        mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".bmp": "image/bmp",
                ".webp": "image/webp"}.get(suffix, "image/jpeg")
        with open(img_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime};base64,{data}"
    except Exception:
        return None


def extract_hash_values(raw_dir: Path) -> list:
    """Look for hash value text files in the raw directory."""
    hashes = []
    for f in raw_dir.rglob("*Hash*"):
        if f.suffix.lower() in {".txt", ".csv", ".md"}:
            try:
                hashes.append({"file": f.name, "content": f.read_text(errors="replace")})
            except Exception:
                pass
    return hashes


def build_timeline(artefacts: dict) -> list:
    """
    Attempts to build a timeline by finding date-like fields
    across all artefact records.
    """
    date_keywords = ["date", "time", "timestamp", "datetime", "created", "sent", "received"]
    events = []

    for artefact_name, content in artefacts.items():
        for record in content.get("records", []):
            date_val = None
            date_key = None
            for k, v in record.items():
                if any(kw in k.lower() for kw in date_keywords) and v and str(v).strip():
                    date_val = str(v).strip()
                    date_key = k
                    break
            if date_val:
                # Get a summary field — first non-date, non-empty value
                summary = ""
                for k, v in record.items():
                    if k != date_key and v and str(v).strip():
                        summary = str(v)[:120]
                        break
                events.append({
                    "date": date_val,
                    "artefact": artefact_name,
                    "summary": summary
                })

    # Sort by date string — works for ISO-format dates
    events.sort(key=lambda x: x["date"])
    return events[:500]  # cap at 500 events for report size


def generate_report(case: dict, normalised: dict, yolo_path: Path,
                    images_dir: Path, investigator: str = "N/A") -> str:
    """
    Generates a fully self-contained HTML forensics report.
    Returns the HTML string.
    """
    case_id   = case.get("id", "unknown")
    case_name = case.get("name", "Unnamed Case")
    created   = case.get("created", "")[:19].replace("T", " ")
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    artefacts = normalised.get("artefacts", {})
    artefact_count = normalised.get("artefact_count", 0)

    # SMS/MMS records
    sms_keywords = ["sms", "message", "mms", "chat", "whatsapp"]
    sms_artefacts = {k: v for k, v in artefacts.items()
                     if any(kw in k.lower() for kw in sms_keywords)}

    # YOLO results
    yolo_data = {"analysed": [], "skipped": []}
    if yolo_path.exists():
        with open(yolo_path, encoding="utf-8") as f:
            yolo_data = json.load(f)

    analysed = yolo_data.get("analysed", [])
    weapon_hits = [r for r in analysed
                   if any(d["source"] == "weapon"
                          for d in r.get("label_summary", []))]
    total_detections = sum(r.get("detection_count", 0) for r in analysed)

    # Hash values
    raw_dir = Path(case["path"]) / "raw"
    hashes = extract_hash_values(raw_dir)

    # Timeline
    timeline = build_timeline(artefacts)

    # ── Build HTML ─────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Forensic Report — {case_name}</title>
<style>
:root {{
    --bg: #ffffff; --bg2: #f6f8fa; --border: #d0d7de;
    --text: #1f2328; --text2: #656d76; --accent: #0969da;
    --badge-bg: #0969da; --badge-text: #fff;
    --weapon-bg: #cf222e; --weapon-text: #fff;
    --header-bg: #0969da; --header-text: #fff;
    --table-head: #f6f8fa; --shadow: rgba(0,0,0,0.1);
}}
body.dark {{
    --bg: #0d1117; --bg2: #161b22; --border: #30363d;
    --text: #c9d1d9; --text2: #8b949e; --accent: #58a6ff;
    --badge-bg: #1f6feb; --badge-text: #fff;
    --weapon-bg: #da3633; --weapon-text: #fff;
    --header-bg: #161b22; --header-text: #58a6ff;
    --table-head: #21262d; --shadow: rgba(0,0,0,0.4);
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Segoe UI',Arial,sans-serif; background:var(--bg);
        color:var(--text); font-size:14px; line-height:1.6; }}
.page {{ max-width:1200px; margin:0 auto; padding:2rem; }}
.report-header {{ background:var(--header-bg); color:var(--header-text);
                  padding:2rem; border-radius:8px; margin-bottom:2rem;
                  box-shadow:0 2px 8px var(--shadow); }}
.report-header h1 {{ font-size:1.6rem; margin-bottom:0.5rem; }}
.report-header p {{ opacity:0.8; font-size:0.9rem; }}
.meta-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr));
              gap:1rem; margin-top:1rem; }}
.meta-item {{ background:rgba(255,255,255,0.1); padding:0.6rem 1rem;
              border-radius:6px; }}
.meta-item .label {{ font-size:0.75rem; opacity:0.7; text-transform:uppercase; }}
.meta-item .value {{ font-size:0.95rem; font-weight:600; margin-top:0.2rem; }}
.section {{ background:var(--bg2); border:1px solid var(--border);
            border-radius:8px; padding:1.5rem; margin-bottom:1.5rem; }}
.section h2 {{ color:var(--accent); font-size:1rem; margin-bottom:1rem;
               padding-bottom:0.5rem; border-bottom:1px solid var(--border); }}
.summary-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr));
                 gap:1rem; }}
.stat-card {{ background:var(--bg); border:1px solid var(--border); border-radius:6px;
              padding:1rem; text-align:center; }}
.stat-card .num {{ font-size:2rem; font-weight:700; color:var(--accent); }}
.stat-card .lbl {{ font-size:0.78rem; color:var(--text2); margin-top:0.2rem; }}
table {{ width:100%; border-collapse:collapse; font-size:0.82rem; }}
th {{ background:var(--table-head); color:var(--text2); padding:0.5rem 0.6rem;
      text-align:left; border-bottom:2px solid var(--border); white-space:nowrap; }}
td {{ padding:0.45rem 0.6rem; border-bottom:1px solid var(--border);
      word-break:break-word; max-width:300px; }}
tr:hover td {{ background:var(--table-head); }}
.table-wrap {{ overflow-x:auto; }}
.badge {{ background:var(--badge-bg); color:var(--badge-text);
          padding:0.15rem 0.5rem; border-radius:10px; font-size:0.75rem; }}
.weapon-badge {{ background:var(--weapon-bg); color:var(--weapon-text);
                 padding:0.2rem 0.6rem; border-radius:10px; font-size:0.75rem;
                 font-weight:600; }}
.img-card {{ display:flex; gap:1rem; background:var(--bg); border:1px solid var(--border);
             border-radius:6px; overflow:hidden; margin-bottom:0.8rem; }}
.img-thumb {{ flex-shrink:0; width:160px; height:120px; object-fit:cover; }}
.img-info {{ padding:0.8rem; flex:1; }}
.img-info .filename {{ color:var(--accent); font-size:0.85rem; margin-bottom:0.4rem; }}
.tags {{ display:flex; flex-wrap:wrap; gap:0.3rem; margin-top:0.4rem; }}
.timeline-item {{ display:flex; gap:1rem; padding:0.5rem 0;
                  border-bottom:1px solid var(--border); font-size:0.82rem; }}
.timeline-date {{ flex-shrink:0; width:160px; color:var(--text2); font-family:monospace; }}
.timeline-artefact {{ flex-shrink:0; width:140px; }}
.timeline-summary {{ flex:1; color:var(--text2); overflow:hidden;
                     text-overflow:ellipsis; white-space:nowrap; }}
.hash-block {{ background:var(--bg); border:1px solid var(--border); border-radius:6px;
               padding:1rem; font-family:monospace; font-size:0.78rem;
               white-space:pre-wrap; word-break:break-all; max-height:200px;
               overflow-y:auto; }}
.theme-toggle {{ position:fixed; top:1rem; right:1rem; z-index:999;
                 background:var(--bg2); border:1px solid var(--border);
                 color:var(--text); padding:0.4rem 0.9rem; border-radius:20px;
                 cursor:pointer; font-size:0.85rem; box-shadow:0 2px 8px var(--shadow); }}
.toc {{ list-style:none; }}
.toc li {{ padding:0.2rem 0; }}
.toc a {{ color:var(--accent); text-decoration:none; font-size:0.9rem; }}
.toc a:hover {{ text-decoration:underline; }}
@media print {{
    .theme-toggle {{ display:none; }}
    body {{ background:#fff; color:#000; }}
}}
</style>
</head>
<body>
<button class="theme-toggle" onclick="toggleTheme()">🌙 Dark / ☀️ Light</button>
<div class="page">

<!-- ── HEADER ──────────────────────────────────────── -->
<div class="report-header">
    <h1>🔍 Digital Forensics Report</h1>
    <p>Android Device Artefact Analysis</p>
    <div class="meta-grid">
        <div class="meta-item">
            <div class="label">Case Name</div>
            <div class="value">{case_name}</div>
        </div>
        <div class="meta-item">
            <div class="label">Case ID</div>
            <div class="value" style="font-family:monospace; font-size:0.8rem;">{case_id}</div>
        </div>
        <div class="meta-item">
            <div class="label">Investigator</div>
            <div class="value">{investigator}</div>
        </div>
        <div class="meta-item">
            <div class="label">Case Created</div>
            <div class="value">{created}</div>
        </div>
        <div class="meta-item">
            <div class="label">Report Generated</div>
            <div class="value">{generated}</div>
        </div>
    </div>
</div>

<!-- ── TABLE OF CONTENTS ───────────────────────────── -->
<div class="section">
    <h2>Table of Contents</h2>
    <ul class="toc">
        <li><a href="#summary">1. Evidence Summary</a></li>
        <li><a href="#artefacts">2. Artefacts Overview</a></li>
        <li><a href="#sms">3. SMS / MMS Records</a></li>
        <li><a href="#images">4. Image Analysis Results</a></li>
        <li><a href="#weapons">5. Weapon Detections</a></li>
        <li><a href="#timeline">6. Event Timeline</a></li>
        {'<li><a href="#hashes">7. Hash Values</a></li>' if hashes else ''}
    </ul>
</div>

<!-- ── 1. EVIDENCE SUMMARY ─────────────────────────── -->
<div class="section" id="summary">
    <h2>1. Evidence Summary</h2>
    <div class="summary-grid">
        <div class="stat-card">
            <div class="num">{artefact_count}</div>
            <div class="lbl">Artefacts Parsed</div>
        </div>
        <div class="stat-card">
            <div class="num">{len(analysed)}</div>
            <div class="lbl">Images Analysed</div>
        </div>
        <div class="stat-card">
            <div class="num">{total_detections}</div>
            <div class="lbl">Total Detections</div>
        </div>
        <div class="stat-card">
            <div class="num" style="color:#da3633;">{len(weapon_hits)}</div>
            <div class="lbl">Weapon Detections</div>
        </div>
        <div class="stat-card">
            <div class="num">{sum(v.get('count',0) for v in artefacts.values() if isinstance(v,dict))}</div>
            <div class="lbl">Total Records</div>
        </div>
        <div class="stat-card">
            <div class="num">{len(timeline)}</div>
            <div class="lbl">Timeline Events</div>
        </div>
    </div>
</div>

<!-- ── 2. ARTEFACTS OVERVIEW ───────────────────────── -->
<div class="section" id="artefacts">
    <h2>2. Artefacts Overview</h2>
    <div class="table-wrap">
    <table>
        <thead><tr><th>#</th><th>Artefact</th><th>Records</th></tr></thead>
        <tbody>
"""

    for i, (name, content) in enumerate(artefacts.items(), 1):
        count = content.get("count", "—") if isinstance(content, dict) else "error"
        html += f"<tr><td>{i}</td><td>{name}</td><td><span class='badge'>{count}</span></td></tr>\n"

    html += """        </tbody>
    </table>
    </div>
</div>

<!-- ── 3. SMS / MMS RECORDS ───────────────────────── -->
<div class="section" id="sms">
    <h2>3. SMS / MMS Records</h2>
"""

    for artefact_name, content in sms_artefacts.items():
        records = content.get("records", [])
        if not records:
            continue
        cols = list(records[0].keys())
        html += f"<h3 style='font-size:0.9rem; color:var(--text2); margin:1rem 0 0.5rem;'>{artefact_name} — {len(records)} records</h3>\n"
        html += "<div class='table-wrap'><table><thead><tr>"
        for col in cols:
            html += f"<th>{col}</th>"
        html += "</tr></thead><tbody>"
        for record in records:
            html += "<tr>"
            for val in record.values():
                html += f"<td>{val}</td>"
            html += "</tr>"
        html += "</tbody></table></div>\n"

    html += "</div>\n"

    # ── 4. IMAGE ANALYSIS ─────────────────────────────────
    html += """<div class="section" id="images">
    <h2>4. Image Analysis Results</h2>
"""
    if analysed:
        for item in analysed:
            fname = item.get("file", "")
            size_kb = round(item.get("size_bytes", 0) / 1024, 1)
            detections = item.get("detection_count", 0)
            labels = item.get("label_summary", [])

            img_path = images_dir / fname
            img_src = encode_image(img_path) if img_path.exists() else None

            html += f"""<div class="img-card">
    {'<img class="img-thumb" src="' + img_src + '">' if img_src else '<div class="img-thumb" style="background:#21262d; display:flex; align-items:center; justify-content:center; color:#555; font-size:0.75rem;">No preview</div>'}
    <div class="img-info">
        <div class="filename">📷 {fname}</div>
        <div style="font-size:0.78rem; color:var(--text2); margin-bottom:0.4rem;">
            Size: {size_kb} KB &nbsp;|&nbsp; {detections} detection(s)
        </div>
        <div class="tags">
"""
            if labels:
                for det in labels:
                    css = "weapon-badge" if det["source"] == "weapon" else "badge"
                    count_str = f" ×{det['count']}" if det["count"] > 1 else ""
                    html += f'<span class="{css}">{det["label"]}{count_str} ({det["max_confidence"]})</span>\n'
            else:
                html += '<span style="color:var(--text2); font-size:0.78rem;">No objects detected</span>'

            html += """        </div>
    </div>
</div>
"""
    else:
        html += "<p style='color:var(--text2);'>No image analysis results available.</p>"

    html += "</div>\n"

    # ── 5. WEAPON DETECTIONS ──────────────────────────────
    html += """<div class="section" id="weapons">
    <h2>5. Weapon Detections</h2>
"""
    if weapon_hits:
        html += f"<p style='margin-bottom:1rem; color:var(--text2);'>{len(weapon_hits)} image(s) with weapon detections.</p>"
        for item in weapon_hits:
            fname = item.get("file", "")
            img_path = images_dir / fname
            img_src = encode_image(img_path) if img_path.exists() else None
            weapon_labels = [d for d in item.get("label_summary", [])
                             if d["source"] == "weapon"]

            html += f"""<div class="img-card" style="border-color:#da3633;">
    {'<img class="img-thumb" src="' + img_src + '">' if img_src else '<div class="img-thumb" style="background:#2a0f0f; display:flex; align-items:center; justify-content:center; color:#f85149; font-size:0.75rem;">No preview</div>'}
    <div class="img-info">
        <div class="filename" style="color:#f85149;">⚠️ {fname}</div>
        <div class="tags" style="margin-top:0.4rem;">
"""
            for det in weapon_labels:
                count_str = f" ×{det['count']}" if det["count"] > 1 else ""
                html += f'<span class="weapon-badge">{det["label"]}{count_str} — confidence: {det["max_confidence"]}</span>\n'

            html += """        </div>
    </div>
</div>
"""
    else:
        html += "<p style='color:var(--text2);'>No weapon detections found.</p>"

    html += "</div>\n"

    # ── 6. TIMELINE ───────────────────────────────────────
    html += """<div class="section" id="timeline">
    <h2>6. Event Timeline</h2>
"""
    if timeline:
        html += f"<p style='color:var(--text2); font-size:0.82rem; margin-bottom:1rem;'>Showing up to 500 most recent events sorted by date.</p>"
        html += "<div style='max-height:500px; overflow-y:auto;'>"
        for event in timeline:
            html += f"""<div class="timeline-item">
    <div class="timeline-date">{event['date']}</div>
    <div class="timeline-artefact"><span class="badge">{event['artefact']}</span></div>
    <div class="timeline-summary">{event['summary']}</div>
</div>
"""
        html += "</div>"
    else:
        html += "<p style='color:var(--text2);'>No timeline events found.</p>"

    html += "</div>\n"

    # ── 7. HASH VALUES ────────────────────────────────────
    if hashes:
        html += """<div class="section" id="hashes">
    <h2>7. Hash Values</h2>
"""
        for h in hashes:
            html += f"<p style='font-weight:600; margin-bottom:0.3rem;'>{h['file']}</p>"
            html += f"<div class='hash-block'>{h['content']}</div>\n"
        html += "</div>\n"

    # ── FOOTER ────────────────────────────────────────────
    html += f"""<div style="text-align:center; color:var(--text2); font-size:0.78rem;
                padding:2rem 0; border-top:1px solid var(--border); margin-top:2rem;">
    Generated by Android Forensics Tool &nbsp;|&nbsp; {generated} &nbsp;|&nbsp; Case: {case_id}
</div>

</div><!-- .page -->
<script>
function toggleTheme() {{
    document.body.classList.toggle('dark');
    localStorage.setItem('theme', document.body.classList.contains('dark') ? 'dark' : 'light');
}}
// Restore saved theme
if (localStorage.getItem('theme') === 'dark') document.body.classList.add('dark');
</script>
</body>
</html>"""

    return html