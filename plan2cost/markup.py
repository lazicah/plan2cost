"""The annotated plan: every wall in the drawing model drawn on the original drawing with its id, so a person can see exactly what was measured
and correct it. External walls are red, internal blue, and walls with an open issue are ringed in orange."""
import tempfile

import cv2

from plan2cost.drawing_model import DrawingModel

RED, BLUE, ORANGE = (40, 40, 220), (200, 90, 20), (0, 150, 255)  # BGR


def plan_image(model: DrawingModel, pdf: str | None, page: int | None, image: str | None, dpi: int = 150):
    """The plan as a picture, and how many pixels there are to a millimetre of the real building (from the model's calibration)."""
    cal = model.calibrations[0]
    if image:
        return cv2.imread(image), 1.0 / cal.mm_per_unit
    from plan2cost.pdf import render_pages

    if cal.unit == "px":  # a raster-route page: its lengths are in pixels of the render it was read from (250 dpi)
        dpi = int(cal.detail.get("dpi", dpi))
        return cv2.imread(render_pages(pdf, [page], tempfile.mkdtemp(), dpi=dpi)[0]), 1.0 / cal.mm_per_unit
    return cv2.imread(render_pages(pdf, [page], tempfile.mkdtemp(), dpi=dpi)[0]), (dpi / 72) / cal.mm_per_unit


def draw_markup(model: DrawingModel, out_path: str, pdf: str | None = None, page: int | None = None, image: str | None = None, max_side: int = 2400,
                margin_m: float = 2.5) -> str:
    """Draw the model's walls on the page (a vector or raster PDF page) or on the image it was read from. Returns the path written."""
    img, scale = plan_image(model, pdf, page, image, 150)
    flagged = {i for issue in model.issues if issue.severity != "info" for i in issue.elements}
    h, w = img.shape[:2]
    thick = max(3, int(max(h, w) / 700))
    font = max(0.6, max(h, w) / 2600)
    xs, ys = [], []
    for e in model.walls():
        p1, p2 = (int(e.x0_mm * scale), int(e.y0_mm * scale)), (int(e.x1_mm * scale), int(e.y1_mm * scale))
        colour = RED if e.subtype == "external" else BLUE
        if e.id in flagged:
            cv2.line(img, p1, p2, ORANGE, thick + 6)
        cv2.line(img, p1, p2, colour, thick)
        xs += [p1[0], p2[0]]
        ys += [p1[1], p2[1]]
    for o in model.openings():  # openings: a green bar across the wall at the gap
        p1, p2 = (int(o.x0_mm * scale), int(o.y0_mm * scale)), (int(o.x1_mm * scale), int(o.y1_mm * scale))
        cv2.line(img, p1, p2, (60, 170, 60), thick + 4)
        xs += [p1[0], p2[0]]
        ys += [p1[1], p2[1]]
    for e in model.walls():  # labels last so they sit on top of every line
        mid = (int((e.x0_mm + e.x1_mm) / 2 * scale), int((e.y0_mm + e.y1_mm) / 2 * scale))
        pos = (mid[0] + (int(18 * font) if e.orient == "v" else 0), mid[1] + (int(18 * font) if e.orient == "h" else 0))
        label = e.id.replace("W-", "")
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font, 2)
        cv2.rectangle(img, (pos[0] - 2, pos[1] - th - 3), (pos[0] + tw + 2, pos[1] + 3), (255, 255, 255), -1)
        cv2.putText(img, label, pos, cv2.FONT_HERSHEY_SIMPLEX, font, RED if e.subtype == "external" else BLUE, 2)
    for o in model.openings():
        mid = (int((o.x0_mm + o.x1_mm) / 2 * scale), int((o.y0_mm + o.y1_mm) / 2 * scale))
        label = o.id + (f" {o.mark}" if o.mark else "")
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font * 0.8, 2)
        cv2.rectangle(img, (mid[0] + 6, mid[1] - th - 8), (mid[0] + tw + 10, mid[1] + 2), (255, 255, 255), -1)
        cv2.putText(img, label, (mid[0] + 8, mid[1] - 4), cv2.FONT_HERSHEY_SIMPLEX, font * 0.8, (40, 130, 40), 2)
    m = int(margin_m * 1000 * scale)
    x0, y0, x1, y1 = max(min(xs) - m, 0), max(min(ys) - m, 0), min(max(xs) + m, w), min(max(ys) + m, h)
    crop = img[y0:y1, x0:x1].copy()
    k = max_side / max(crop.shape[:2])
    if k < 1:
        crop = cv2.resize(crop, (int(crop.shape[1] * k), int(crop.shape[0] * k)), interpolation=cv2.INTER_AREA)
    legend = f"{model.floor} floor, page {model.page}: red external, blue internal, orange has an open issue, green openings. Numbers are wall ids (W-nnn)."
    cv2.rectangle(crop, (0, 0), (crop.shape[1], 34), (255, 255, 255), -1)
    cv2.putText(crop, legend, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (30, 30, 30), 1)
    cv2.imwrite(out_path, crop)
    return out_path


def _add_review(model: DrawingModel, markup_path: str) -> None:
    """Append the model's review of the annotated plan as issues. A failed or empty review never stops the run or changes a measurement."""
    from plan2cost.drawing_model import Issue
    from plan2cost.review import review_model

    try:
        model.issues += review_model(model, markup_path)
    except Exception as e:  # the model could not be reached or answered badly
        model.issues.append(Issue("review_skipped", "info", f"The model review of the plan was skipped ({type(e).__name__}).", [], "", "model review"))


def model_for_page(pdf: str, page: int, floor: str, out_dir: str, review: bool = False) -> DrawingModel:
    """Interpret one page, build the verified drawing model, save it with its annotated plan, and return it."""
    from pathlib import Path

    from plan2cost.drawing_model import build_model
    from plan2cost.interpret import interpret_page

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    r = interpret_page(pdf, page, str(out / "scratch"), keep=True)
    if "error" in r or "_walls" not in r:
        raise ValueError(r.get("error", "no walls were kept for the drawing model (the legacy detector does not keep them)"))
    model = build_model(r, floor, page)
    name = f"markup_{floor}_p{page}.jpg"
    draw_markup(model, str(out / name), pdf=pdf, page=page, image=r.get("_image") if r["route"] == "raster" else None)
    model.markup = name
    if review:
        _add_review(model, str(out / name))
    model.save(out / f"drawing_model_{floor}_p{page}.json")
    return model


def model_for_image(path: str, floor: str, out_dir: str, facts: dict | None = None, review: bool = False) -> DrawingModel:
    """The same for a plan supplied as an image. `facts` are the printed facts the model read (stated scale, overall dimensions); read now if absent."""
    from pathlib import Path

    from plan2cost.drawing_model import build_model
    from plan2cost.interpret import interpret_image
    from plan2cost.page_facts import read_page_facts

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    facts = facts or read_page_facts(path)
    r = interpret_image(path, facts, keep_walls=True)
    if "error" in r:
        raise ValueError(r["error"])
    r["route"] = "raster"
    r["confidence"] = "medium" if "printed overall dimensions fit" in r["scale"] and r.get("building") else "low"
    model = build_model(r, floor, 1, printed_mm=facts.get("horizontal_mm", []) + facts.get("vertical_mm", []))
    name = f"markup_{floor}.jpg"
    draw_markup(model, str(out / name), image=path)
    model.markup = name
    if review:
        _add_review(model, str(out / name))
    model.save(out / f"drawing_model_{floor}.json")
    return model
