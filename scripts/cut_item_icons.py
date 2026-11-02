"""Cut a generated 4x4 item sheet into one 128x128 icon per item, each centred in its own square.

The sheet is a white-background grid of 16 items (see the cell order in CELLS). Every item is
found as the connected non-white pieces that lie mostly in its cell, so an item that spills over
its cell edge is kept whole and a neighbour's overhang is left out. The item is moved so that the
centre of its bounding box is the centre of its square, scaled to 128x128 and cut to a rounded
square (the corners are transparent).

    uv run --with pillow --with numpy python scripts/cut_item_icons.py assets/items/sources/sheet-2.png assets/items

A single regenerated item (one item on a white background) replaces one icon instead; it is scaled so
that the longer side of the item matches the others (about ITEM_LONG_SIDE of the 128 pixels):

    uv run --with pillow --with numpy python scripts/cut_item_icons.py \
        --single dice assets/items/sources/dice-2.png assets/items

A sheet drawn as pixel art (each item on an ART_SIZE x ART_SIZE grid, scaled up by an integer factor)
is read back pixel for pixel instead, so the icons stay crisp:

    uv run --with pillow --with numpy python scripts/cut_item_icons.py \
        --pixel-art assets/items/sources/sheet-3.png assets/items

1. The sheet's pixel grid is found: the block size from the sheet size, the offset (0 to block-1 in each
   direction) as the one that makes the blocks most uniform.
2. Each block becomes one art pixel: its most frequent colour, so the soft edges of a generated image
   do not mix into it. The colours are then reduced to one shared palette of PALETTE_SIZE.
3. Each item is centred in its cell by whole art pixels, and the ART_SIZE x ART_SIZE cell is scaled up
   with nearest neighbour to 128x128 (2x for 64) and cut to a rounded square.
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
ITEM_LONG_SIDE = 104  # the longer side of an item in a 128 icon: about the median of the sheet's items
ART_SIZE = 64  # pixel-art mode: the art pixels of one cell (ICON_SIZE must be a multiple)
PALETTE_SIZE = 32  # pixel-art mode: the colours shared by all items

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


def cut(sheet_path: Path, output_dir: Path) -> list[Placement]:
    """Write one icon per cell as <name>.png and return how each item was moved."""
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
        icon = Image.fromarray(square).resize((ICON_SIZE, ICON_SIZE), Image.Resampling.LANCZOS).convert("RGBA")
        icon.putalpha(mask)
        icon.save(output_dir / f"{name}.png", optimize=True)
        placements.append(Placement(name, shift_x, shift_y))
    return placements


def cut_single(image_path: Path, output_dir: Path, name: str) -> None:
    """Write <name>.png from an image of one item, scaled to the size of the others and centred."""
    pixels = np.asarray(Image.open(image_path).convert("RGB")).copy()
    foreground = pixels.min(axis=2) <= WHITE_THRESHOLD
    pixels[~foreground] = 255  # an off-white background would show as a faint box on the white icon
    ys, xs = np.nonzero(foreground)
    item = Image.fromarray(pixels[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1])
    scale = ITEM_LONG_SIDE / max(item.size)
    item = item.resize((round(item.width * scale), round(item.height * scale)), Image.Resampling.LANCZOS)
    icon = Image.new("RGB", (ICON_SIZE, ICON_SIZE), (255, 255, 255))
    icon.paste(item, ((ICON_SIZE - item.width) // 2, (ICON_SIZE - item.height) // 2))
    icon = icon.convert("RGBA")
    icon.putalpha(rounded_mask())
    output_dir.mkdir(parents=True, exist_ok=True)
    icon.save(output_dir / f"{name}.png", optimize=True)


def find_grid(pixels: np.ndarray, block: int) -> tuple[int, int]:
    """Return the (x, y) offset of the pixel grid: the one whose blocks vary least inside."""
    offsets = [(offset_x, offset_y) for offset_y in range(block) for offset_x in range(block)]
    return min(offsets, key=lambda offset: _blocks(pixels, block, *offset).astype(float).std(axis=(1, 3)).mean())


def _blocks(pixels: np.ndarray, block: int, offset_x: int, offset_y: int) -> np.ndarray:
    """Return the whole blocks from the offset, shaped (rows, block, columns, block, 3)."""
    rows = (pixels.shape[0] - offset_y) // block
    columns = (pixels.shape[1] - offset_x) // block
    area = pixels[offset_y : offset_y + rows * block, offset_x : offset_x + columns * block]
    return area.reshape(rows, block, columns, block, 3)


def read_art(pixels: np.ndarray, block: int, offset_x: int, offset_y: int) -> np.ndarray:
    """Return one art pixel per block: the block's most frequent colour."""
    blocks = _blocks(pixels, block, offset_x, offset_y)
    rows, _, columns, _, _ = blocks.shape
    packed = (blocks[..., 0].astype(np.int64) << 16) | (blocks[..., 1].astype(np.int64) << 8) | blocks[..., 2]
    packed = packed.transpose(0, 2, 1, 3).reshape(rows * columns, block * block)
    ordered = np.sort(packed, axis=1)
    starts = np.ones_like(ordered, dtype=bool)
    starts[:, 1:] = ordered[:, 1:] != ordered[:, :-1]
    art = np.empty(rows * columns, dtype=np.int64)
    for index in range(rows * columns):  # the longest run of one colour in each sorted block
        bounds = np.flatnonzero(np.append(starts[index], True))
        art[index] = ordered[index, bounds[np.argmax(np.diff(bounds))]]
    rgb = np.stack([(art >> 16) & 255, (art >> 8) & 255, art & 255], axis=1).astype(np.uint8)
    return rgb.reshape(rows, columns, 3)


def cut_pixel_art(sheet_path: Path, output_dir: Path) -> tuple[int, int, int]:
    """Write one crisp icon per cell from a pixel-art sheet; return the block size and grid offset."""
    pixels = np.asarray(Image.open(sheet_path).convert("RGB"))
    block = pixels.shape[0] // (GRID * ART_SIZE)
    offset_x, offset_y = find_grid(pixels, block)
    art = read_art(pixels, block, offset_x, offset_y)
    art[art.min(axis=2) > WHITE_THRESHOLD] = 255
    quantized = Image.fromarray(art).quantize(PALETTE_SIZE, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    art = np.asarray(quantized.convert("RGB")).copy()
    art[art.min(axis=2) > WHITE_THRESHOLD] = 255

    foreground = art.min(axis=2) <= WHITE_THRESHOLD
    labels = label_pieces(foreground)
    owners: dict[int, int] = {}
    for label in range(1, labels.max() + 1):
        ys, xs = np.nonzero(labels == label)
        owners[label] = int(
            np.bincount((ys // ART_SIZE).clip(0, GRID - 1) * GRID + (xs // ART_SIZE).clip(0, GRID - 1)).argmax()
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    mask = rounded_mask()
    for index, name in enumerate(CELLS):
        row, column = divmod(index, GRID)
        ys, xs = np.nonzero(np.isin(labels, [label for label, owner in owners.items() if owner == index]))
        shift_y = round(row * ART_SIZE + (ART_SIZE - 1) / 2 - (ys.min() + ys.max()) / 2)
        shift_x = round(column * ART_SIZE + (ART_SIZE - 1) / 2 - (xs.min() + xs.max()) / 2)
        cell = np.full((ART_SIZE, ART_SIZE, 3), 255, dtype=np.uint8)
        target_y, target_x = ys + shift_y - row * ART_SIZE, xs + shift_x - column * ART_SIZE
        inside = (target_y >= 0) & (target_y < ART_SIZE) & (target_x >= 0) & (target_x < ART_SIZE)
        cell[target_y[inside], target_x[inside]] = art[ys[inside], xs[inside]]
        icon = Image.fromarray(cell).resize((ICON_SIZE, ICON_SIZE), Image.Resampling.NEAREST).convert("RGBA")
        icon.putalpha(mask)
        icon.save(output_dir / f"{name}.png", optimize=True)
    return block, offset_x, offset_y


if __name__ == "__main__":
    if sys.argv[1] == "--pixel-art":
        block, offset_x, offset_y = cut_pixel_art(Path(sys.argv[2]), Path(sys.argv[3]))
        print(f"block {block}px, grid offset ({offset_x}, {offset_y})")
    elif sys.argv[1] == "--single":
        cut_single(Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[2])
    else:
        for placement in cut(Path(sys.argv[1]), Path(sys.argv[2])):
            print(placement)
