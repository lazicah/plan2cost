"""The rooms of a floor plan as printed: name and the two internal dimensions beside it. The model copies what is printed; code checks that each
number is in the page's text layer (when it has one) and does the arithmetic. A room whose dimensions are not both printed is kept, with its area
unknown, so it is asked about and never guessed. Rooms are taken as rectangles, which is what a printed pair of internal dimensions means."""
import re
from dataclasses import dataclass, field

from plan2cost.kit.client import chat_json, image_part

PROMPT = """You are reading a floor plan for a quantity surveyor. List every ROOM or enclosed space on this floor (bedrooms, bathrooms, kitchen, lounge, store,
lobby, porch, terrace, balcony, stairs...). For each, copy exactly what is printed:
- the name as printed;
- the two internal dimensions printed inside or beside the room, in millimetres as printed. Rooms often show one number along each side; if only one or none
  is printed, use null for the missing one.
- where the space is on the picture, as a box [x0, y0, x1, y1] in fractions of the picture's width and height (from the top left), as tight as you can around its floor area; null if you cannot tell.
Never calculate, estimate or guess a dimension. Do not use door or window widths or grid dimensions. Reply with JSON only:
{"rooms": [{"name": str, "a_mm": number|null, "b_mm": number|null, "box": [x0, y0, x1, y1]|null, "note": str}]}"""

OPEN_WORDS = ("porch", "terrace", "balcony", "veranda", "verandah", "patio", "carport", "deck", "courtyard", "garden")  # open air: no external wall can cross one; a different finish, asked about
VOID_WORDS = ("void", "open to below", "open above", "double height", "double-height", "atrium", "light well")  # open between floors: no slab
CIRCULATION_WORDS = ("lobby", "corridor", "hallway", "passage", "landing", "walkway", "foyer", "hall")  # a long way through that connects rooms: internal, enclosed
WET_WORDS = ("bath", "wc", "toilet", "shower", "vis.", "w.c", "powder", "ensuite", "en-suite")


@dataclass
class Room:
    """A room or space as named on the plan, with its two internal dimensions when both are printed, whether it is open air, a wet room, and where it is on the picture. `kind` says what the name means."""
    name: str
    a_mm: float | None
    b_mm: float | None
    floor: str = ""
    verified: bool = False  # both numbers found in the page's text layer
    note: str = ""
    open_space: bool = False
    box: tuple | None = None  # where the space is, as fractions of the picture (x0, y0, x1, y1), as the model saw it
    wet: bool = False
    issues: list = field(default_factory=list)

    @property
    def kind(self) -> str:
        """What the name says the space is: outdoor (open air), void (open between floors), circulation (a walkway connecting rooms), wet, or room."""
        low = self.name.lower()
        if any(w in low for w in VOID_WORDS):
            return "void"
        if self.open_space:
            return "outdoor"
        if self.wet:
            return "wet"
        return "circulation" if any(w in low for w in CIRCULATION_WORDS) else "room"

    @property
    def area_m2(self) -> float | None:
        return round(self.a_mm * self.b_mm / 1e6, 2) if self.a_mm and self.b_mm else None

    @property
    def perimeter_m(self) -> float | None:
        return round(2 * (self.a_mm + self.b_mm) / 1000, 2) if self.a_mm and self.b_mm else None


def valid_box(b) -> tuple | None:
    """A box of fractions (x0, y0, x1, y1) with a positive size on the picture, else None."""
    try:
        x0, y0, x1, y1 = (float(v) for v in b)
    except (TypeError, ValueError):
        return None
    return (x0, y0, x1, y1) if 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1 else None


def printed(value: float, text: str) -> bool:
    """Is this number printed on the page, as a whole number and not part of a longer one?"""
    return bool(re.search(rf"(?<![\d.]){int(value)}(?![\d])", text))


def to_rooms(data: dict, text: str, floor: str) -> list[Room]:
    """Keep what is printed. A dimension that is not in the text layer is dropped to null and the room says so."""
    rooms = []
    for r in data.get("rooms", []):
        name = str(r.get("name", "")).strip()
        if not name:
            continue
        dims = []
        issues = []
        for key in ("a_mm", "b_mm"):
            v = r.get(key)
            if v is not None and text.strip() and not printed(float(v), text):
                issues.append(f"{key[0]}={v} is not printed on the page, so it was not used")
                v = None
            dims.append(float(v) if v else None)
        low = name.lower()
        room = Room(name, dims[0], dims[1], floor, bool(text.strip()) and all(dims), str(r.get("note", "")), any(w in low for w in OPEN_WORDS), valid_box(r.get("box")),
                    any(w in low for w in WET_WORDS), issues)
        if not (room.a_mm and room.b_mm):
            room.issues.append("both internal dimensions are not printed: area unknown")
        rooms.append(room)
    return rooms


def read_rooms(image_path: str, text: str, floor: str) -> list[Room]:
    """The rooms of a floor plan picture: the model copies the names, printed sizes and rough places; code checks the numbers against the text layer."""
    return to_rooms(chat_json([{"type": "text", "text": PROMPT}, image_part(image_path)]), text, floor)
