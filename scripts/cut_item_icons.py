# /// script
# requires-python = ">=3.14"
# dependencies = ["numpy>=2", "pillow>=11"]
# ///
"""Cut a generated 4x4 item sheet into one 128x128 icon per item, each centred in its own square.

The sheet is a white-background grid of 16 items (see the cell order in CELLS). Every item is
found as the connected non-white pieces that lie mostly in its cell, so an item that spills over
its cell edge is kept whole and a neighbour's overhang is left out. The item is moved so that the
centre of its bounding box is the centre of its square, scaled to 128x128 and cut to a rounded
square (the corners are transparent).

Its dependencies are declared inline (PEP 723), so `uv run` runs it in its own environment.

    uv run scripts/cut_item_icons.py assets/items/sources/sheet-2.png assets/items

Naming items after the output directory writes only those icons, e.g. one item from a newer sheet:

    uv run scripts/cut_item_icons.py assets/items/sources/sheet-3.png assets/items dice
"""

import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

GRID = 4
ICON_SIZE = 128
CORNER_RADIUS = 20
BLOCK = 4  # pieces are found on a grid of BLOCK x BLOCK pixels, which is fast and ignores single stray pixels
WHITE_THRESHOLD = 235  # a pixel whose channels are all above this is background
MAX_FILL = 0.85  # an item larger than this share of its square is scaled down, leaving at least 7.5% white each side

# the items of the sheet, left to right and top to bottom; those not in db_data/items.py are spares
CELLS = [
    "omamori", "id_card", "alarm_clock", "dash_shoes",
    "weekly_pass", "dice", "treat", "past_life_shard",
    "coffee", "locker_key", "onigiri", "umbrella",
    "business_bag", "sticky_notes", "potted_plant", "hourglass",
]  # fmt: skip


@dataclass(frozen=True)
class Placement:
    """How far an item was moved to centre it, in sheet pixels."""

    name: str
    shift_x: int
    shift_y: int
    scale: float = 1.0  # below 1 when the item was scaled down to keep the white margin


def label_pieces(foreground: np.ndarray) -> np.ndarray:
    """Label the 8-connected foreground pieces of a mask (0 is background)."""
    labels = np.zeros(foreground.shape, dtype=int)
    height, width = foreground.shape
    current = 0
    for y, x in zip(*np.nonzero(foreground), strict=True):
        if labels[y, x]:
            continue
        current += 1
        labels[y, x] = current
        queue = deque([(y, x)])
        while queue:
            cy, cx = queue.popleft()
            for ny in range(max(cy - 1, 0), min(cy + 2, height)):
                for nx in range(max(cx - 1, 0), min(cx + 2, width)):
                    if foreground[ny, nx] and not labels[ny, nx]:
                        labels[ny, nx] = current
                        queue.append((ny, nx))
    return labels


def rounded_mask() -> Image.Image:
    """Return the alpha mask of a rounded square, drawn large for smooth corners."""
    scale = 4
    mask = Image.new("L", (ICON_SIZE * scale, ICON_SIZE * scale), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, ICON_SIZE * scale - 1, ICON_SIZE * scale - 1), radius=CORNER_RADIUS * scale, fill=255
    )
    return mask.resize((ICON_SIZE, ICON_SIZE), Image.Resampling.LANCZOS)


def cut(sheet_path: Path, output_dir: Path, only: set[str] | None = None) -> list[Placement]:
    """Write one icon per cell (or only the named ones) as <name>.png and return how each item was moved."""
    pixels = np.asarray(Image.open(sheet_path).convert("RGB"))
    cell = pixels.shape[0] // GRID
    foreground = pixels.min(axis=2) <= WHITE_THRESHOLD
    blocks = foreground[: cell * GRID, : cell * GRID].reshape(cell * GRID // BLOCK, BLOCK, -1, BLOCK).any(axis=(1, 3))
    labels = label_pieces(blocks)
    cells_per_block = cell // BLOCK
    owners: dict[int, int] = {}
    for label in range(1, labels.max() + 1):
        ys, xs = np.nonzero(labels == label)
        owners[label] = int(np.bincount((ys // cells_per_block) * GRID + xs // cells_per_block).argmax())

    output_dir.mkdir(parents=True, exist_ok=True)
    mask = rounded_mask()
    placements = []
    for index, name in enumerate(CELLS):
        if only and name not in only:
            continue
        row, column = divmod(index, GRID)
        mine = np.isin(labels, [label for label, owner in owners.items() if owner == index])
        selected = np.repeat(np.repeat(mine, BLOCK, axis=0), BLOCK, axis=1) & foreground[: cell * GRID, : cell * GRID]
        ys, xs = np.nonzero(selected)
        shift_y = round(row * cell + (cell - 1) / 2 - (ys.min() + ys.max()) / 2)
        shift_x = round(column * cell + (cell - 1) / 2 - (xs.min() + xs.max()) / 2)
        square = np.full((cell, cell, 3), 255, dtype=np.uint8)
        target_y, target_x = ys + shift_y - row * cell, xs + shift_x - column * cell
        inside = (target_y >= 0) & (target_y < cell) & (target_x >= 0) & (target_x < cell)
        square[target_y[inside], target_x[inside]] = pixels[ys[inside], xs[inside]]
        square, scale = fit_margin(square, target_y[inside], target_x[inside])
        icon = Image.fromarray(square).resize((ICON_SIZE, ICON_SIZE), Image.Resampling.LANCZOS).convert("RGBA")
        icon.putalpha(mask)
        icon.save(output_dir / f"{name}.png", optimize=True)
        placements.append(Placement(name, shift_x, shift_y, round(float(scale), 3)))
    return placements


def fit_margin(square: np.ndarray, ys: np.ndarray, xs: np.ndarray) -> tuple[np.ndarray, float]:
    """Scale the item at (ys, xs) down to MAX_FILL of the square if it is larger, keeping it centred."""
    size = square.shape[0]
    top, bottom, left, right = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    scale = min(1.0, MAX_FILL * size / max(bottom - top, right - left))
    if scale == 1.0:
        return square, scale
    item = Image.fromarray(square[top:bottom, left:right])
    item = item.resize((round(item.width * scale), round(item.height * scale)), Image.Resampling.LANCZOS)
    fitted = Image.new("RGB", (size, size), (255, 255, 255))
    fitted.paste(item, ((size - item.width) // 2, (size - item.height) // 2))
    return np.asarray(fitted), scale


if __name__ == "__main__":
    for placement in cut(Path(sys.argv[1]), Path(sys.argv[2]), set(sys.argv[3:]) or None):
        print(placement)
