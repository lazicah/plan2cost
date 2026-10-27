# plan2 truth: foundation section

Girth keys say 230 (thickness as drawn); the sheet labels that column 225mm BLOCK.
Source: the author's surveyed workbook (General works.xlsx, plan2), values only. Green cells of `Substructure` plus `FDN Tre-Girth` M121 and M123.
Drawings (kept out of git): `reference/plan2/` architectural and structural PDFs.

| key | cell | value | meaning |
|---|---|---|---|
| strip_trench_girth_230_m | FDN Tre-Girth!M121 | 70 | strip trench girth (grid lines, after pad-base and overlap deductions) |
| fdn_blockwork_girth_230_m | FDN Tre-Girth!M123 | 105 | foundation blockwork girth (full runs, no pad deductions) |
| topsoil_strip_m2 | Substructure!E19 | 226 | topsoil removal area |
| trench_excavation_strip_m3 | Substructure!E32 | 58 | strip trench excavation, 225 blocks |
| pit_excavation_column_bases_m3 | Substructure!E80 | 48 | pit excavation for column bases |
| working_space_m3 | Substructure!E120 | 180 | working space allowance |
| levelling_compaction_m2 | Substructure!E152 | 89 | levelling and compaction of excavation bottom |
| excavated_surface_treatment_m2 | Substructure!E181 | 300 | surface treatment to excavated surfaces (BoQ adds E152) |
| blinding_part1_m3 | Substructure!E223 | 7 | blinding, first part (BoQ adds F405) |
| blinding_part2_m3 | Substructure!F405 | 10 | blinding, second part |
| strip_footing_concrete_m3 | Substructure!E231 | 11 | foundation footing concrete |
| column_base_concrete_m3 | Substructure!E264 | 12 | column bases concrete |
| column_concrete_m3 | Substructure!E296 | 2.61 | isolated columns concrete |
| ground_slab_m3 | Substructure!E328 | 30 | ground slab concrete |
| brc_mesh_part1_m2 | Substructure!E329 | 200 | fabric reinforcement, first part |
| brc_mesh_part2_m2 | Substructure!E338 | 0 | fabric reinforcement, second part |
| dpm_polythene_m2 | Substructure!E330 | 200 | polythene damp-proof membrane |
| fdn_blockwork_230_m2 | Substructure!E341 | 89 | 230mm blockwork in foundation |
| disposal_off_site_m3 | Substructure!E355 | 53 | excavated material removed off site |
| backfill_around_foundations_m3 | Substructure!E359 | 53 | backfilling around foundations |
| hardcore_m3 | Substructure!F408 | 28 | hardcore filling |
| laterite_m3 | Substructure!F411 | 28 | laterite filling |
| external_wall_render_m2 | Substructure!E619 | 89 | external wall rendering below DPC |

Zero-valued cells are omitted (the scorer divides by truth). BoQ lines add some parts: surface treatment = E181 + E152; blinding = E223 + F405; fabric = E329 + E338.

## How the values are built (traced backwards from `BOQs`)
- Trench girth (M121) = ROUNDUP(sum over grid lines of [full runs - deductions]). Each grid block lists runs (length x number), then "Ddts": pad-base widths (1.2-1.7m x count, excavated separately as pits) and wall-overlap deductions (0.23, 0.115). 69.69 -> 70.
- Foundation blockwork girth (M123) = ROUNDUP(sum of the full runs, no pad deductions) = 104.835 -> 105.
- Trench excavation E32 = 70 x 0.69 wide x 1.20 deep (1350 - 150 topsoil) = 57.96 -> 58.
- Foundation blockwork E341 = 105 x 0.85 high (1350 - 150 topsoil - 350 footing) = 89.25 -> 89 m2.
- Footing concrete E231 = 70 x 0.69 x 0.225 = 10.87 -> 11 m3.
- Working space allowance: 2 sides x trench girth 70 x 0.6 wide x depth, summed with the pad-base working space (E120).
Correction (author, 2026-10-27): footing width is 675mm on the structural drawing = 0.675m, which BESMM4 1.5.2 rounds to 0.68m. The sheet used 0.69.
`trench_excavation_strip_m3` in truth.json is therefore 57 (70 x 0.68 x 1.2 = 57.12), not the sheet's 58. Footing concrete stays 11 (10.71).
Not yet re-derived with 0.68: blinding (E223, F405) and anything else that reads the sheet's 0.69 (D184, D226, D29).
