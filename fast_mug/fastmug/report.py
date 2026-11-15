"""Word (.docx) clinical report with charts and patient snapshots."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from docx import Document
from docx.enum.section import WD_ORIENT  # noqa: F401
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from . import APP_LONG_NAME, __version__
from . import charts
from .protocol import PURSUIT_HZ
from .scoring import BY_KEY, CATALOG, DOMAINS, NEURO_DOMAINS
from .storage import Store

INK = RGBColor(0x1F, 0x29, 0x33)
MUTED = RGBColor(0x6B, 0x77, 0x85)
STATUS_HEX = {"ok": "2E9E6B", "watch": "C98F12", "alert": "C9423B", "na": "A7B1BC"}
STATUS_TINT = {"ok": "E7F5EE", "watch": "FBF1DC", "alert": "F8E3E1", "na": "EEF1F4"}
STATUS_WORD = {"ok": "Within baseline", "watch": "Watch", "alert": "Alert", "na": "Not measured"}
FONT = "Calibri"


# --------------------------------------------------------------------------- #
# docx helpers
# --------------------------------------------------------------------------- #
def _shade(cell, hex_fill: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tcPr.append(shd)


def _borders(table, color: str = "D5DCE4", inner: bool = True) -> None:
    tbl = table._tbl
    tblPr = tbl.tblPr
    b = OxmlElement("w:tblBorders")
    edges = ("top", "left", "bottom", "right") + (("insideH", "insideV") if inner else ())
    for e in edges:
        el = OxmlElement("w:" + e)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        b.append(el)
    tblPr.append(b)


def _left_bar(cell, hex_color: str, size: int = 36) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    el = OxmlElement("w:left")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(size))
    el.set(qn("w:space"), "0")
    el.set(qn("w:color"), hex_color)
    borders.append(el)
    tcPr.append(borders)


def _cell_margins(cell, top=80, bottom=80, left=120, right=120) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for k, v in (("top", top), ("bottom", bottom), ("start", left), ("end", right)):
        el = OxmlElement("w:" + k)
        el.set(qn("w:w"), str(v))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tcPr.append(mar)


def _run(par, text: str, size: float = 10, bold: bool = False, color: RGBColor = INK,
         italic: bool = False):
    r = par.add_run(text)
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.color.rgb = color
    r.font.name = FONT
    return r


def _para(container, text: str = "", size: float = 10, bold: bool = False, color: RGBColor = INK,
          space_after: float = 4, align=None):
    p = container.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.space_before = Pt(0)
    if align is not None:
        p.alignment = align
    if text:
        _run(p, text, size, bold, color)
    return p


def _heading(doc, text: str, level: int = 1):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14 if level == 1 else 8)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    _run(p, text, 13.5 if level == 1 else 11, True, INK)
    return p


def _field(par, instr: str) -> None:
    r = par.add_run()
    b = OxmlElement("w:fldChar")
    b.set(qn("w:fldCharType"), "begin")
    t = OxmlElement("w:instrText")
    t.set(qn("xml:space"), "preserve")
    t.text = instr
    e = OxmlElement("w:fldChar")
    e.set(qn("w:fldCharType"), "end")
    r._r.append(b)
    r._r.append(t)
    r._r.append(e)
    r.font.size = Pt(8)
    r.font.color.rgb = MUTED


def _fmt_time(iso: str) -> str:
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return d.strftime("%d %b %Y, %H:%M UTC")
    except (ValueError, AttributeError):
        return iso or "—"


def mission_day(settings, iso: str) -> Optional[int]:
    try:
        start = datetime.fromisoformat(str(settings.get("mission.start_utc")).replace("Z", ""))
        now = datetime.fromisoformat(iso.replace("Z", "")).replace(tzinfo=None)
        return (now - start).days + 1
    except (ValueError, TypeError, AttributeError):
        return None


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def build_report(session: Dict, store: Store, settings, out_path: Optional[Path] = None) -> Path:
    folder = Path(session["folder"])
    figdir = folder / "figures"
    figdir.mkdir(exist_ok=True)
    verdict = session["verdict"]
    scored = verdict["metrics"]
    raw = session["raw_metrics"]
    crew = session.get("crew", {})
    traces = store.load_traces(session)
    window = int(settings.get("exam.baseline_window", 10))
    history = store.history(session["crew_id"], window, exclude_id=session["id"])
    past = [s for s in store.sessions(session["crew_id"]) if s.get("id") != session["id"]][-12:]
    ex = settings.get("exam", {})

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    for side in ("left_margin", "right_margin"):
        setattr(sec, side, Cm(2.0))
    sec.top_margin, sec.bottom_margin = Cm(1.8), Cm(1.8)
    st = doc.styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(10)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)

    # header / footer
    hp = sec.header.paragraphs[0]
    _run(hp, APP_LONG_NAME, 8, False, MUTED)
    _run(hp, "      Confidential medical information", 8, False, MUTED)
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _run(fp, "Screening and decision support only, not a diagnosis.   Page ", 8, False, MUTED)
    _field(fp, "PAGE")
    _run(fp, " of ", 8, False, MUTED)
    _field(fp, "NUMPAGES")

    # title block
    p = _para(doc, space_after=2)
    _run(p, "%s report" % session.get("type_title", "Exam"), 20, True, INK)
    md = mission_day(settings, session.get("started_utc", ""))
    sub = "%s, %s" % (crew.get("name", "Crew member"), _fmt_time(session.get("started_utc", "")))
    if md is not None and md > 0:
        sub += ", mission day %d" % md
    _para(doc, sub, 11, False, MUTED, space_after=10)

    info = doc.add_table(rows=2, cols=4)
    info.alignment = WD_TABLE_ALIGNMENT.CENTER
    _borders(info)
    heads = ("Crew member", "Role", "Mission", "Exam")
    vals = (crew.get("name", "—"), crew.get("role", "—") or "—",
            "%s, %s" % (settings.get("mission.name"), settings.get("mission.vehicle")),
            "%s, %.0f s, camera %s fps%s" % (session.get("type_title"), session.get("duration_s", 0),
                                            session.get("camera_fps") or "—",
                                            ", simulated" if session.get("simulated") else ""))
    for i, (h, v) in enumerate(zip(heads, vals)):
        c0, c1 = info.cell(0, i), info.cell(1, i)
        _shade(c0, "F3F5F8")
        for c in (c0, c1):
            _cell_margins(c)
        c0.paragraphs[0].paragraph_format.space_after = Pt(0)
        _run(c0.paragraphs[0], h, 8, False, MUTED)
        c1.paragraphs[0].paragraph_format.space_after = Pt(0)
        _run(c1.paragraphs[0], str(v), 9.5, False, INK)
    _set_widths(info, (4.2, 3.4, 4.4, 5.0))

    # verdict
    _para(doc, space_after=6)
    level = verdict["level"]
    vt = doc.add_table(rows=1, cols=1)
    cell = vt.cell(0, 0)
    _shade(cell, STATUS_TINT.get(level, "EEF1F4"))
    _left_bar(cell, STATUS_HEX.get(level, "A7B1BC"))
    _cell_margins(cell, 140, 140, 220, 200)
    _set_widths(vt, (17.0,))
    cp = cell.paragraphs[0]
    cp.paragraph_format.space_after = Pt(2)
    _run(cp, verdict["headline"], 15, True, RGBColor.from_string(STATUS_HEX.get(level, "1F2933")))
    lines = _verdict_lines(session)
    for ln in lines:
        q = cell.add_paragraph()
        q.paragraph_format.space_after = Pt(1)
        _run(q, ln, 10, False, INK)

    _heading(doc, "Recommended actions")
    for r in verdict["recommendations"]:
        q = doc.add_paragraph(style="List Bullet")
        q.paragraph_format.space_after = Pt(2)
        _run(q, r, 10)

    # domain summary
    _heading(doc, "Summary by domain")
    dt = doc.add_table(rows=1, cols=4)
    _borders(dt)
    for i, h in enumerate(("Domain", "Status", "Index", "Flagged measures")):
        c = dt.cell(0, i)
        _shade(c, "F3F5F8")
        _cell_margins(c)
        c.paragraphs[0].paragraph_format.space_after = Pt(0)
        _run(c.paragraphs[0], h, 8.5, True, MUTED)
    for dk in list(NEURO_DOMAINS) + ["alert"]:
        d = verdict["domains"].get(dk)
        if not d:
            continue
        row = dt.add_row().cells
        for c in row:
            _cell_margins(c)
            c.paragraphs[0].paragraph_format.space_after = Pt(0)
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        _run(row[0].paragraphs[0], d["name"], 10, True)
        _shade(row[1], STATUS_TINT[d["status"]])
        _run(row[1].paragraphs[0], STATUS_WORD[d["status"]], 9.5, True,
             RGBColor.from_string(STATUS_HEX[d["status"]]))
        _run(row[2].paragraphs[0], "—" if d["index"] is None else "%.0f / 100" % d["index"], 9.5)
        flags = ", ".join(BY_KEY[k].label for k in d["flags"]) or "None"
        _run(row[3].paragraphs[0], flags, 9.5, False, INK if d["flags"] else MUTED)
    _set_widths(dt, (3.4, 3.0, 2.4, 8.2))

    # figures
    figs: List[tuple] = []
    f = charts.midline_chart(raw, scored, history, figdir / "midline.png")
    if f:
        figs.append((f, "Right and left side performance, each relative to the personal baseline. "
                        "A short bar on one side points to weakness on that side."))
    f = charts.zprofile_chart(scored, float(ex.get("watch_z", 2)), float(ex.get("alert_z", 3)),
                              figdir / "zprofile.png")
    if f:
        figs.append((f, "Deviation of every scored measure from baseline. Shaded bands mark the "
                        "watch and alert thresholds."))
    _heading(doc, "Measurement overview")
    for path, cap in figs:
        _figure(doc, path, cap)

    snaps = session.get("snapshots", [])
    if snaps:
        _heading(doc, "Patient images")
        _para(doc, "Camera view, not mirrored: the patient's right side is on the image left. "
                   "Overlays show the tracked landmarks and the facial midline.", 9, False, MUTED)
        _image_grid(doc, folder, snaps)

    sig = []
    for fn, args, cap in (
            (charts.tapping_chart, (traces, figdir / "tapping.png"),
             "Thumb-to-index gap in hand-size units. Look for slowing, smaller amplitude or "
             "fading on one side."),
            (charts.ram_chart, (traces, figdir / "ram.png"),
             "Palm rotation while turning both hands. Gravity-independent replacement for the "
             "arm drift test."),
            (charts.speech_chart, (traces, figdir / "speech.png"),
             "Lip aperture while repeating pa-ta-ka and its rhythm spectrum."),
            (charts.eyes_chart, (traces, figdir / "eyes.png"),
             "Eyelid openness during relaxed fixation. PERCLOS counts time below 0.2."),
            (charts.oculomotor_chart, (traces, session.get("saccade_trials", []), PURSUIT_HZ,
                                       figdir / "oculomotor.png"),
             "Gaze following a moving target, and the reaction time of each saccade trial.")):
        try:
            p = fn(*args)
        except Exception:  # noqa: BLE001
            p = None
        if p:
            sig.append((p, cap))
    if sig:
        _heading(doc, "Signals recorded")
        for p, cap in sig:
            _figure(doc, p, cap)

    trend_keys = ["arm.tap_symmetry", "face.smile_symmetry", "speech.ddk_rate",
                  "eyes.pursuit_coherence", "alert.perclos", "alert.saccade_latency_ms"]
    p = charts.trend_chart(past, session, trend_keys, figdir / "trend.png")
    if p:
        _heading(doc, "Trend")
        _figure(doc, p, "Recent sessions, oldest to newest. Grey band: baseline mean ± 2 SD. "
                        "Red dots are neuro exams, the open circle is this session.")

    # self report
    sr = session.get("self_report") or {}
    if sr:
        _heading(doc, "Self-report")
        t = doc.add_table(rows=0, cols=2)
        _borders(t)
        rows = [("Mood", _scale(sr.get("mood"))), ("Sleep quality", _scale(sr.get("sleep_quality"))),
                ("Sleep last night", "%s h" % sr.get("sleep_hours", "—")),
                ("Stress", _scale(sr.get("stress"))),
                ("Symptoms", ", ".join(sr.get("symptoms", [])) or "None reported"),
                ("Symptom onset", sr.get("onset") or "—"),
                ("Notes", sr.get("notes") or "—")]
        for k, v in rows:
            c = t.add_row().cells
            for x in c:
                _cell_margins(x)
                x.paragraphs[0].paragraph_format.space_after = Pt(0)
            _run(c[0].paragraphs[0], k, 9.5, False, MUTED)
            _run(c[1].paragraphs[0], str(v), 9.5)
        _set_widths(t, (4.0, 13.0))

    # full table
    _heading(doc, "All measurements")
    mt = doc.add_table(rows=1, cols=6)
    _borders(mt)
    for i, h in enumerate(("Measure", "Value", "Baseline", "n", "z", "Status")):
        c = mt.cell(0, i)
        _shade(c, "F3F5F8")
        _cell_margins(c, 60, 60, 100, 100)
        c.paragraphs[0].paragraph_format.space_after = Pt(0)
        _run(c.paragraphs[0], h, 8.5, True, MUTED)
    last_dom = None
    for defn in CATALOG:
        s = scored.get(defn.key)
        if not s or not defn.scored:
            continue
        if defn.domain != last_dom:
            last_dom = defn.domain
            r = mt.add_row().cells
            m = r[0].merge(r[5])
            _shade(m, "FAFBFC")
            _cell_margins(m, 60, 40, 100, 100)
            m.paragraphs[0].paragraph_format.space_after = Pt(0)
            _run(m.paragraphs[0], DOMAINS[defn.domain], 9, True, INK)
        r = mt.add_row().cells
        for c in r:
            _cell_margins(c, 40, 40, 100, 100)
            c.paragraphs[0].paragraph_format.space_after = Pt(0)
        _run(r[0].paragraphs[0], defn.label, 9)
        _run(r[1].paragraphs[0], "%s %s" % (defn.format(s["value"]), defn.unit), 9)
        _run(r[2].paragraphs[0], "%s ± %s" % (defn.format(s["mean"]), defn.format(s["sd"])), 9, False, MUTED)
        _run(r[3].paragraphs[0], "%d%s" % (s["n"], "" if s["source"] == "personal" else "*"), 9, False, MUTED)
        _run(r[4].paragraphs[0], "—" if s["z"] is None else "%+.1f" % s["z"], 9)
        _run(r[5].paragraphs[0], STATUS_WORD[s["status"]], 9, True, RGBColor.from_string(STATUS_HEX[s["status"]]))
    _set_widths(mt, (5.6, 2.6, 3.4, 1.0, 1.4, 3.0))
    _para(doc, "* Fewer than %d personal daily checks on file; reference values were blended into the "
               "baseline." % int(ex.get("min_personal_sessions", 3)), 8.5, False, MUTED, space_after=2)

    _heading(doc, "Method")
    for line in (
        "Camera-only exam. Face and hand landmarks are tracked with MediaPipe; all values are "
        "computed on the device and compared with this crew member's rolling baseline from the "
        "last %d daily checks (median and robust spread)." % window,
        "In weightlessness the arm drift test loses meaning because the limb no longer falls, so "
        "motor strength is screened with finger tapping and rapid hand turning, compared side to "
        "side. Facial measures are referenced to the in-flight baseline because fluid shift "
        "changes facial shape.",
        "Timing measures include camera and display latency, which is constant on a given setup "
        "and cancels against the personal baseline.",
        "This report supports a flight surgeon's assessment. It does not establish or exclude "
        "stroke, TIA or any other diagnosis.",
    ):
        q = _para(doc, line, 9, False, INK, space_after=4)
    _para(doc, "Generated by %s %s" % (APP_LONG_NAME, __version__), 8, False, MUTED)

    out = out_path or folder / ("report_%s_%s.docx" % (session.get("type"), session["id"]))
    doc.save(str(out))
    return out


def _verdict_lines(session: Dict) -> List[str]:
    v = session["verdict"]
    out = []
    side = session.get("weaker_side")
    if side and v["neuro_status"] in ("watch", "alert"):
        out.append("Findings are lateralised: the %s side is weaker on paired measures."
                   % ("left" if side == "L" else "right"))
    flagged = []
    for dk in DOMAINS:
        d = v["domains"].get(dk)
        if d and d["flags"]:
            flagged += [BY_KEY[k].label.lower() for k in d["flags"] if v["metrics"][k]["status"] == "alert"]
    if flagged:
        out.append("Alert-level measures: " + ", ".join(flagged) + ".")
    if v.get("discordant"):
        out.append("Self-reported wellbeing does not match the objective alertness measures.")
    syms = (session.get("self_report") or {}).get("symptoms") or []
    if syms:
        out.append("Reported symptoms: " + ", ".join(syms) + ".")
    if not session.get("valid", True):
        out.append("Several measures could not be computed. Repeat the exam with the face and "
                   "hands fully visible.")
    if not out:
        out.append("All measures are within this crew member's baseline.")
    return out


def _scale(v) -> str:
    if v is None or v == "":
        return "—"
    return "%s of 5" % v


def _set_widths(table, cms) -> None:
    """Fixed column widths that both Word and LibreOffice respect."""
    table.autofit = False
    grid = table._tbl.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), cms):
        gc.set(qn("w:w"), str(int(Cm(w).twips)))
    for row in table.rows:
        for cell, w in zip(row.cells, cms):
            cell.width = Cm(w)


def _figure(doc, path: Path, caption: str, width_cm: float = 16.5) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(str(path), width=Cm(width_cm))
    _para(doc, caption, 8.5, False, MUTED, space_after=10)


def _image_grid(doc, folder: Path, snaps: List[Dict]) -> None:
    cols = 2
    t = doc.add_table(rows=0, cols=cols)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i in range(0, len(snaps), cols):
        cells = t.add_row().cells
        for c, snap in zip(cells, snaps[i:i + cols]):
            _cell_margins(c, 60, 60, 60, 60)
            p = c.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            img = folder / snap["file"]
            if img.exists():
                p.add_run().add_picture(str(img), width=Cm(8.0))
            q = c.add_paragraph()
            q.alignment = WD_ALIGN_PARAGRAPH.CENTER
            q.paragraph_format.space_after = Pt(4)
            _run(q, snap.get("caption", ""), 8.5, False, MUTED)
