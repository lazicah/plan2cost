# Run 004: plan6 whole document, muse-spark-1.3

2026-10-28 10:57

The model indexed every page of the set, classified each page, then read the opening schedules and section levels.

## Page roles

| page | role | title |
|---|---|---|
| 1 | cover | Proposed Residential Estate Development for Box City Sculpture, on Iwo Road, Ibadan, Oyo State |
| 2 | site | LAYOUT |
| 3 | site | CALLOUT I |
| 4 | site | CALLOUT II |
| 5 | site | CALLOUT III |
| 6 | floor_plan | GROUND FLOOR PLAN |
| 7 | floor_plan | FIRST FLOOR PLAN |
| 8 | roof_plan | ROOF PLAN |
| 9 | section | SECTION A |
| 10 | section | SECTION B |
| 11 | section | SECTION C |
| 12 | section | SECTION D |
| 13 | elevation | APPROACH ELEVATION |
| 14 | elevation | RIGHT SIDE ELEVATION |
| 15 | elevation | REAR ELEVATION |
| 16 | elevation | LEFT SIDE ELEVATION |
| 17 | ceiling_plan | GROUND FLOOR RCP |
| 18 | ceiling_plan | FIRST FLOOR RCP |
| 19 | detail | STAIRCASE DETAIL I |
| 20 | detail | STAIRCASE DETAIL II |
| 21 | floor_plan | GROUND FLOOR INDICATOR PLAN |
| 22 | floor_plan | FIRST FLOOR INDICATOR PLAN |
| 23 | opening_schedule | AW1 & AW2 |
| 24 | opening_schedule | AW3 & AW4 |
| 25 | opening_schedule | TD1 & TD2 |
| 26 | opening_schedule | TD3 & GD1 |
| 27 | opening_schedule | SD1 & ASD1 |

## Opening types vs the author's survey

| mark | result |
|---|---|
| AW1 | ok |
| AW2 | ok |
| AW3 | ok |
| AW4 | ok |
| TD1 | ok |
| TD2 | ok |
| TD3 | ok |
| GD1 | ok |
| SD1 | WRONG |
| ASD1 | ok |

## Levels read from the sections

```json
{
  "levels": [
    {
      "name": "Building Apex Level",
      "value_mm": 7800,
      "page": 9
    },
    {
      "name": "Roof Base Level",
      "value_mm": 6600,
      "page": 9
    },
    {
      "name": "First Floor Level",
      "value_mm": 3600,
      "page": 9
    },
    {
      "name": "Ground Floor Level",
      "value_mm": 600,
      "page": 9
    },
    {
      "name": "NGL",
      "value_mm": 0,
      "page": 9
    },
    {
      "name": "Building Apex Level",
      "value_mm": 7800,
      "page": 10
    },
    {
      "name": "Roof Base Level",
      "value_mm": 6600,
      "page": 10
    },
    {
      "name": "First Floor Level",
      "value_mm": 3600,
      "page": 10
    },
    {
      "name": "Ground Floor Level",
      "value_mm": 600,
      "page": 10
    },
    {
      "name": "NGL",
      "value_mm": 0,
      "page": 10
    }
  ],
  "storey_heights_mm": [
    {
      "from": "NGL",
      "to": "Ground Floor Level",
      "value_mm": 600
    },
    {
      "from": "Ground Floor Level",
      "to": "First Floor Level",
      "value_mm": 3000
    },
    {
      "from": "First Floor Level",
      "to": "Roof Base Level",
      "value_mm": 3000
    },
    {
      "from": "Roof Base Level",
      "to": "Building Apex Level",
      "value_mm": 1200
    }
  ],
  "questions": [
    "Internal room clear height dimensions (2700mm range) are partially legible on sections - please confirm if separate floor-to-ceiling heights apply for QS measurement?"
  ]
}
```

## Notes

Whole 27-page set read: page titles from the title block, schedules from pages 23-27, levels from the sections. SD1 height: drawing prints 2150, the author's sheet uses 2100.

## Questions the agent asked instead of guessing

- AW2 description footer reads 'Grand total: 2' which disagrees with QUANTITY 20 and location Grand total: 20 - QUANTITY 20 used.
- AW1 and AW2 location tables list individual WINDOW NO. / ROOM NO. entries that are partly illegible in the images; only floor levels GROUND FLR. LEVL and FIRST FLR. LEVEL extracted, room-by-room allocation not verified against Grand totals.
- No location / floor table printed for TD1, TD2, TD3, GD1, SD1, ASD1 - floors left empty.
- Internal room clear height dimensions (2700mm range) are partially legible on sections - please confirm if separate floor-to-ceiling heights apply for QS measurement?
