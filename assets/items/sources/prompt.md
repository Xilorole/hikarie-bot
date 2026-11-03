# Item sheet prompt

The prompt for generating a new item sheet with gpt-image-2, rebuilt from the first sheet's prompt so that
every sheet matches `sheet-2.png`. Pass `sheet-2.png` as the only reference image, change only the cells that
are being redrawn (keep the others as they are, so the whole sheet stays consistent), generate the whole sheet,
and cut only the redrawn items from it.

The cells follow `CELLS` in `scripts/cut_item_icons.py`; a new item takes a spare cell (those not in
`db_data/items.py`) or replaces one.

```text
Redraw the attached item sheet as one new 1024x1024 sprite sheet.

Reference (the only one): keep each item's design, colors, materials, pose, pixel-art style and dark-fantasy
dungeon-loot mood, and redraw every item. Only the cells described as changed below differ.

Grid: a 4x4 grid of 16 cells, each exactly 256x256 pixels, aligned to multiples of 256. No gaps, borders or
grid lines.

Style (identical for all 16 items):
- 16-bit dungeon-crawler loot icons: everyday office objects shown as relics.
- One shared palette of about 32 colors. Near-black outline (#1a1220), one art pixel wide, around every item.
- Light from the top-left: one flat highlight and one or two flat shadow tones per material, plus a single
  bright specular pixel on metal, glass and gems.
- Worn texture made of a few deliberate pixels, not noise. No blur and no soft glow; sparkles are solid pixels.

Composition (identical for all 16 items):
- Each item centered in its cell, its longer side about 208 of 256 pixels, with an even margin on every side.
- 3/4 view, slightly tilted. No ground shadow. Solid flat pure white background (#FFFFFF).
- No text, no letters, no numbers, no logos, no watermark.

Cells, left to right, top to bottom:
1. omamori: green cloth charm pouch with a stitched four-leaf clover, gold cord tied in a bow, a small grey
   stone tied to the cord, a few green sparkle pixels
2. employee ID card: plastic card on a blue lanyard with a metal clip, a gold IC chip and a blank photo
   silhouette
3. alarm clock: aged brass twin-bell alarm clock with a hammer between the bells and short motion ticks beside
   the bells
4. dash shoes: a single low-cut black technical trail running shoe in side 3/4 view, toe pointing left. Dark
   grey honeycomb mesh upper with layered black synthetic overlays and a few small light grey accents, a bungee
   quick-lace with a toggle lock, a pull loop at the heel, a well-cushioned black midsole and an aggressive
   lugged outsole. No spring, no metal parts, no logo. Two or three short teal speed lines behind the heel.
5. weekly pass: worn parchment pass with five round red stamped seals in a row and a perforated edge, a few
   green sparkle pixels
6. dice: four-sided ivory board game die, a triangular pyramid in 3/4 view showing two faces, one dark round pip
   on the left face and two on the right face
7. treat: black cast-iron pot with its lid tilted open, a round golden loaf of fresh bread inside, a wisp of
   steam
8. fragment of a past life: pale-blue crystal shard with a swirl of light inside, blue sparkle pixels around it
9. coffee: paper coffee cup with a black lid and a brown sleeve, a curl of steam
10. supply locker key: ornate brass key on a ring with a blank metal tag
11. onigiri: rice ball wrapped in nori, a few green sparkle pixels
12. umbrella: closed navy umbrella with a brass band and a carved wooden crook handle
13. business bag: battered brown leather briefcase with a quilted pattern and brass clasps
14. sticky notes: stack of yellow notes with an arcane circle doodle on the top note, one corner curled
15. potted plant: green office plant in a cracked terracotta pot, a few green sparkle pixels
16. hourglass: carved wooden hourglass with golden sand falling, gold sparkle pixels
```

Describe a redrawn item in words rather than passing a photo of it as a second reference: a second reference
breaks the one-reference rule, and a product photo invites logos.
