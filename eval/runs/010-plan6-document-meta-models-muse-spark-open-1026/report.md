# Run 010: plan6 whole document, meta-models/muse-spark-open-1026

2026-10-28 22:26

The model indexed every page of the set, classified each page, then read the opening schedules and section levels.

## Page roles

| page | role | title |
|---|---|---|
| 1 | cover | Proposed Residential Estate Development for Box City Sculpture, on Iwo Road, Ibadan, Oyo State |
| 2 | site | LAYOUT |
| 3 | detail | CALLOUT I |
| 4 | detail | ALLOUT II |
| 5 | detail | ALLOUT III |
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
      "name": "NGL",
      "value_mm": 0,
      "page": 9
    },
    {
      "name": "GROUND FLR. LEVL",
      "value_mm": 600,
      "page": 9
    },
    {
      "name": "FIRST FLR. LEVEL",
      "value_mm": 3600,
      "page": 9
    },
    {
      "name": "ROOF BASE LEVEL",
      "value_mm": 6600,
      "page": 9
    },
    {
      "name": "BUILDING APEX LEVEL",
      "value_mm": 7800,
      "page": 9
    },
    {
      "name": "NGL",
      "value_mm": 0,
      "page": 10
    },
    {
      "name": "GROUND FLR. LEVL",
      "value_mm": 600,
      "page": 10
    },
    {
      "name": "FIRST FLR. LEVEL",
      "value_mm": 3600,
      "page": 10
    },
    {
      "name": "ROOF BASE LEVEL",
      "value_mm": 6600,
      "page": 10
    },
    {
      "name": "BUILDING APEX LEVEL",
      "value_mm": 7800,
      "page": 10
    }
  ],
  "storey_heights_mm": [
    {
      "from": "NGL",
      "to": "GROUND FLR. LEVL",
      "value_mm": 600
    },
    {
      "from": "GROUND FLR. LEVL",
      "to": "FIRST FLR. LEVEL",
      "value_mm": 3000
    },
    {
      "from": "FIRST FLR. LEVEL",
      "to": "ROOF BASE LEVEL",
      "value_mm": 3000
    },
    {
      "from": "ROOF BASE LEVEL",
      "to": "BUILDING APEX LEVEL",
      "value_mm": 1200
    }
  ],
  "questions": [
    "Left-hand dimension string shows 600, 3000, 3000, 1200 corroborating level differences; confirm these are the intended floor-to-floor heights and datum is NGL 0.",
    "Additional printed vertical figures 2700, 2900 on page 9 and 2700, 2100, 1800 on page 10 appear without explicit from-to labels; confirm if these are clear floor-to-ceiling/sill heights and their reference (top of structural slab vs finished floor vs soffit).",
    "No other printed level figures for natural ground level variations; confirm NGL 0 is uniform across both sections."
  ]
}
```

## Notes

Same whole-document read as run 4, on Muse Spark Open (Baseten).

## Questions the agent asked instead of guessing

- AW2 quantity 20 disagrees with AW2 LOCATION table count: 4 entries under GROUND FLR. LEVEL + 17 entries under FIRST FLR. LEVEL = 21 entries vs Grand total: 20 and QUANTITY 20
- AW1 LOCATION and AW2 LOCATION tables contain several WINDOW NO. entries with blank LOCATION (ROOM NO) cells (e.g., AW1 WG006, WG009b, WG008; AW2 WG002b, WG018a, W105, W116 etc.) - room allocation incomplete
- No location/floor tables provided for TD1, TD2, TD3, GD1, SD1, ASD1 - floors left empty per rules
- Left-hand dimension string shows 600, 3000, 3000, 1200 corroborating level differences; confirm these are the intended floor-to-floor heights and datum is NGL 0.
- Additional printed vertical figures 2700, 2900 on page 9 and 2700, 2100, 1800 on page 10 appear without explicit from-to labels; confirm if these are clear floor-to-ceiling/sill heights and their reference (top of structural slab vs finished floor vs soffit).
- No other printed level figures for natural ground level variations; confirm NGL 0 is uniform across both sections.
