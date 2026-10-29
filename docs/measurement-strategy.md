# Measuring plans and elevations with a vision model

Status: design, Oct 28. To be validated by the spike in `eval/`.

## Core principle

**The model reads; code measures.** Vision models are good at reading text, recognising symbols and understanding layout. They are unreliable at estimating lengths from pixels. So the model never "eyeballs" a length. It extracts *what is written and what is where*, and deterministic code turns that into quantities, checks them against each other, and refuses to guess when they disagree.

Every quantity Plan2Cost produces carries:
- **value** and unit
- **source**: `stated` (read from a dimension string), `scaled` (measured from geometry using a verified scale), `assumed` (a default the user accepted), or `user` (typed in)
- **evidence**: drawing, region (bounding box) and the dimension strings used
- **confidence**: high / medium / low, from the checks below

## Pipeline

```
1 triage -> 2 prepare -> 3 read (vision) -> 4 geometry (SAM 3.1 / CV)
  -> 5 scale -> 6 reconcile -> 7 elevations -> 8 take-off -> 9 verify + ask
```

### 1. Triage the input
Classify each page before doing anything else, because the best method depends on the type:

| Input | Best route |
|---|---|
| Vector PDF from CAD | Extract text and lines directly (PyMuPDF). Exact, cheap, no vision needed for numbers. Use vision only for semantics such as room names and which dimension belongs to which wall. |
| Raster scan or image export | Full vision pipeline. |
| Phone photo of a print | Perspective-correct first (find the sheet corners), then the vision pipeline. |
| Hand sketch | Vision reads the written dimensions. Geometry is not to scale, so rely on stated dimensions only, and ask for the missing ones. |

The model also labels the drawing type (floor plan, elevation, section, roof plan, site plan, schedule, title block) and reads the title block: scale, units, sheet size, and "NTS" (not to scale).

### 2. Prepare the image
- Render PDFs at 300 DPI or more. Deskew, and boost contrast for scans.
- **Tile** large sheets into overlapping crops (e.g. 1024 px with 15% overlap) so small dimension text is legible. Run one whole-sheet pass for layout, then one pass per tile for text.
- Keep a single pixel coordinate system for the sheet, so detections from every tile map back to the same place.

### 3. Read with the vision model (structured output)
Ask the model to return JSON matching a schema. It reads; it does not calculate:
- **Dimension strings**: the text exactly as written ("3600", "3.6", "12'-6\""), plus the pixel coordinates of the extension-line endpoints, orientation, and which chain it belongs to (running or overall).
- **Rooms**: name, label position, and the dimension strings that bound it.
- **Openings**: tag (D1, W2), position, the host wall, swing or type.
- **Schedules**: door and window schedule tables, read into rows.
- **Level annotations** (elevations and sections): FFL, sill, lintel, eaves, ridge, e.g. "+3.000".
- **Notes**: wall thickness (225 mm or 150 mm block), floor-to-ceiling height, materials.

**Robustness:**
- Run the read 2–3 times, or once per tile plus once whole-sheet, and **vote**. Strings that disagree get low confidence.
- Normalise units in code, not in the model. Infer mm, m or ft-in from the title block and the magnitude of the numbers ("3600" on a house plan is mm), and flag anything ambiguous.

### 4. Geometry: walls, rooms and openings
Two independent sources, so they can check each other:
- **SAM 3.1** with text prompts ("wall", "door", "window", "room") gives masks, which become polygons.
- **Classical CV** (OpenCV) as a fallback and cross-check: thick-line detection and morphology for walls, plus contour detection for enclosed rooms.

Unproven: how well SAM 3.1 segments walls on line drawings rather than photos. Spike it early, and keep the CV path working regardless.

### 5. Establish the scale (the crux)
Scale evidence in order of trust:
1. **Stated dimensions.** Each dimension string matched to its endpoints gives a pixels-per-mm estimate. With several, take the median and reject outliers.
2. **Scale bar**, if one is drawn.
3. **Stated scale** ("1:100"), together with sheet size and render DPI. This is invalid if the print was resized or photographed.
4. **Standard objects** (typical door widths) as a weak sanity check only. Confirm the local norms with Lazarus.
5. **User calibration**: click two points and type the distance. This always beats inference.

Rule: if the estimates disagree by more than about 2%, or the drawing says NTS, then **scaled measurements are disabled**. Only stated dimensions are used, and the agent asks for whatever is missing.

### 6. Reconcile the dimensions (constraint checks)
This step makes the measurements trustworthy, and it is a strong technical-depth story:
- **Chain closure**: the running dimensions along a side must sum to the overall dimension (±10 mm).
- **Opposite sides**: on a rectangular building, the front overall should equal the rear overall.
- **Room + wall check**: the room's internal dimensions plus wall thicknesses must equal the external chain.
- **Plan vs elevation**: the width of each elevation must equal the matching plan side.
- **Solve**: treat the dimensions as constraints and solve by least squares, so a single misread string shows up as the residual outlier rather than spreading error everywhere.
- Any check that fails produces a **specific question** to the user ("Front shows 12,450 but the running dims sum to 12,150. Which is right?"), never a silent average.

### 7. Elevations and sections
- Read the **levels**: ground, FFL, sill, lintel/head, ceiling, eaves, ridge. Heights come from level differences (e.g. +3.000 minus +0.150).
- Get the **opening heights** from the elevations, or from the schedule if there is one.
- **Match each elevation to a plan side** by its label (front/rear/left/right, or N/S/E/W) and its width.
- Gables and roof: get the pitch from the elevation or section, then the areas of the gable triangles.
- If there are no elevations, the wall height becomes a flagged `assumed` value that the user confirms.

### 8. Take-off (deterministic code)
- Walls: centre-line girth × height, minus openings. Note internal vs external walls, and walls of different thicknesses.
- Floors: internal area per room, then the gross floor area.
- Openings: count by tag, sizes from the schedule.
- **Measurement rules to be confirmed by Lazarus**: centre-line vs mean girth, the threshold for deducting openings, and which standard to follow (e.g. NIQS BESMM). Implement them as config, not hard-coded.

### 9. Verify, explain, ask
- **Overlay render**: draw every measured wall, room and dimension back onto the drawing, colour-coded by confidence. It lets a human verify at a glance, and it's the hero shot for the demo video.
- **Evidence log** per quantity, as recommended in the Agents 101 workshop. Each BoQ line links back to the regions and strings it came from.
- **Ask only for what blocks progress**, and batch the questions.

## Agent tools

`classify_page`, `extract_pdf_vectors`, `tile_image`, `read_drawing` (vision, schema-bound), `segment` (SAM 3.1), `detect_walls_cv`, `calibrate_scale`, `reconcile_dimensions`, `read_levels`, `compute_takeoff`, `render_overlay`, `ask_user`.

The agent plans with a visible checklist, calls the tools, and finishes only when every quantity is high or medium confidence or the user has confirmed it.

## Evaluation

The ground truth is Lazarus's own surveyed quantities, covering a mix of input types: CAD PDF, scanned print, phone photo and hand sketch.

| Metric | Target to aim for |
|---|---|
| Dimension strings read exactly | ≥ 95% |
| Opening count | exact |
| Floor area error | ≤ 2% |
| Wall area error | ≤ 5% |
| Questions asked per plan | few, and every one justified |

**Ablations for the README and demo**:
- (a) the model alone, asked for quantities directly
- (b) the model reading plus code measuring
- (c) (b) plus reconciliation and scale checks

Compare Muse Spark Open with Muse Spark 1.3 on the same set. The expected story is that (c) beats (a) by a wide margin. That is the technical-depth claim, but only once the eval shows it.

## Known failure modes

These need guards:
- NTS drawings
- resized prints
- feet-and-inches drawings
- mm vs m ambiguity
- rotated text
- the title block mistaken for plan content
- hatching read as walls
- curved or splayed walls
- multi-storey drawings on one sheet
- dimensions to the face of the wall vs to the centre line

## Build order (hackathon)

1. **Today–Oct 29:** spike step 3 (reading dimension strings) on 3 plans for each model. Spike SAM on walls.
2. **Oct 29–30:** scale + reconciliation + take-off, and the overlay render.
3. **Oct 31:** elevations (levels and heights), and the plan↔elevation check.
4. **Nov 1–2:** run the eval, try SAM vs CV, tune the prompts.
