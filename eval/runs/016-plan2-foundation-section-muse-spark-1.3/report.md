# Run 016: plan2 structural foundation section (sheet 01, section A-A), muse-spark-1.3

The model reads the section image; code keeps only numbers printed on the page and checks the layers add up (150 + 775 + 225 + 50 = 1200: True).

| value | printed on the drawing | read | |
|---|---|---|---|
| footing_width_mm | 675 mm | 675 | ok |
| footing_thickness_mm | 225 mm | 225 | ok |
| blinding_mm | 50 mm | 50 | ok |
| slab_mm | 150 mm | 150 | ok |
| fill_depth_mm | 775 mm | 775 | ok |
| overall_depth_mm | 1200 mm | 1200 | ok |

Materials: {'blinding_material': 'SANDCRETE BLINDING', 'mesh': 'A 141'}.
Questions the agent asked instead of guessing: ['Individual hardcore and laterite thicknesses not printed separately; only combined 775mm fill total shown - not split']
