# Item image sources

- `sheet-2.png` is the one and only style reference. Pass exactly this file as the reference image every time a
  new sheet is generated, and never replace it with a newer sheet: generating from a generated image again and
  again degrades the quality.
- Newer sheets were generated from `sheet-2.png` to redraw one item each, and only that item is cut from them:
  - `sheet-3.png`: `dice` (the four-sided die)
  - `sheet-4.png`: `dash_shoes` (the tech shoe, without the spring)

  Every other icon still comes from `sheet-2.png`.

Cut the icons with `scripts/cut_item_icons.py` (see its docstring); name items after the output directory to cut
only those.
