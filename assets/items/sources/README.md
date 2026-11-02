# Item image sources

- `sheet-2.png` is the one and only style reference. Pass exactly this file as the reference image every time a
  new sheet is generated, and never replace it with a newer sheet: generating from a generated image again and
  again degrades the quality.
- `sheet-3.png` was generated from `sheet-2.png`. Only `dice` (the four-sided die) is cut from it; every other
  icon still comes from `sheet-2.png`.

Cut the icons with `scripts/cut_item_icons.py` (see its docstring); name items after the output directory to cut
only those.
