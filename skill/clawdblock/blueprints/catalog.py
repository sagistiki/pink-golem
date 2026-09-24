"""catalog.py — one of every component from parts.py on a row of labelled floor tiles: a visual reference to learn
from (walk along it, or screenshot it) and a regression test for the library.

    python3 skill/clawdblock/blueprints/catalog.py --at 0,-61,40 --facing south
    → jobs/catalog.json   (then: minecraft_run_command commands_file:"jobs/catalog.json" background:true)

Each exhibit sits on a 7x7 quartz tile, the tiles run to the right (i), every tile has a floating name.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from mclib import Build, Frame, parse_args          # noqa: E402
import parts as P                                    # noqa: E402

a = parse_args({"name": "catalog"})
b = Build()
b.before(f"kill @e[type=text_display,tag=catalog]")
TILE = 8
exhibits = []


def exhibit(name):
    def deco(fn):
        exhibits.append((name, fn))
        return fn
    return deco


@exhibit("bed")
def _(f): P.bed(b, f, 3, 1, 3, "light_blue")
@exhibit("chair + table")
def _(f): P.table(b, f, 3, 1, 3); P.chair(b, f, 2, 1, 3, faces="right"); P.chair(b, f, 4, 1, 3, faces="left")
@exhibit("dining set")
def _(f): P.dining_set(b, f, 2, 1, 3, 3)
@exhibit("sofa")
def _(f): P.sofa(b, f, 2, 1, 4, 3, "quartz")
@exhibit("kitchen")
def _(f): P.kitchen(b, f, 1, 1, 5, 5)
@exhibit("fireplace")
def _(f): P.fireplace(b, f, 2, 1, 5, 3, chimney_to=7)
@exhibit("bookshelves")
def _(f): P.bookshelf_wall(b, f, 2, 1, 5, 3, 2)
@exhibit("wardrobe + tv")
def _(f): P.wardrobe(b, f, 1, 1, 5); P.tv_wall(b, f, 3, 1, 5)
@exhibit("lamps")
def _(f):
    P.lamp(b, f, 1, 1, 3, "lantern"); P.lamp(b, f, 3, 1, 3, "modern"); P.lamp(b, f, 5, 1, 3, "table")
@exhibit("chandelier")
def _(f):
    f.box(b, (1, 5, 1), (5, 5, 5), "dark_oak_planks"); P.chandelier(b, f, 3, 5, 3)
@exhibit("window + door")
def _(f):
    f.box(b, (0, 1, 3), (6, 3, 3), "white_concrete"); P.window(b, f, 1, 2, 3, 2, 2); P.doorway(b, f, 4, 1, 3, "spruce", frame="stripped_spruce_log")
@exhibit("gable roof")
def _(f): P.gable_roof(b, f, 1, 1, 5, 5, 1, ridge="k", gable_fill="white_terracotta")
@exhibit("hip roof")
def _(f): P.hip_roof(b, f, 1, 1, 5, 5, 1)
@exhibit("straight stairs")
def _(f): P.straight_stairs(b, f, 3, 1, 1, 4, going="back", stairs="stone_brick_stairs", support="stone_bricks")
@exhibit("spiral stairs")
def _(f):
    c = f.p(3, 1, 3); P.spiral_stairs(b, c[0], c[1], c[1] + 6, c[2])
@exhibit("fountain")
def _(f):
    c = f.p(3, 1, 3); P.fountain(b, c[0], c[1], c[2], 2)
@exhibit("lamp posts")
def _(f):
    for n, s in enumerate(("classic", "modern", "garden")):
        c = f.p(1 + 2 * n, 1, 3); P.lamp_post(b, c[0], c[1], c[2], s)
@exhibit("flower bed")
def _(f):
    c1, c2 = f.p(1, 1, 1), f.p(5, 1, 5); P.flower_bed(b, min(c1[0], c2[0]), c1[1], min(c1[2], c2[2]), max(c1[0], c2[0]), max(c1[2], c2[2]))
@exhibit("striped flag")
def _(f):
    f.box(b, (1, 1, 5), (5, 4, 5), "white_concrete")
    x, y, z = f.p(2, 4, 5)
    fx, fz = {"south": (0, -0.03), "north": (0, 1.03), "east": (-0.03, 0), "west": (1.03, 0)}[f.d("front")]
    P.stripe_display(b, x + fx, y + 0.9, z + fz, f.d("front"), ["red", "orange", "yellow", "lime", "blue", "purple"], width=2.0, tag="catalog")


for n, (name, fn) in enumerate(exhibits):
    f = Frame(*Frame(a.x, a.y, a.z, a.facing).p(n * TILE, 0, 0), a.facing)
    f.box(b, (0, 0, 0), (6, 0, 6), "smooth_quartz")
    f.box(b, (0, 0, 0), (6, 0, 0), "polished_andesite")
    fn(f)
    x, y, z = f.p(3, 0, -1)
    P.label(b, x + 0.5, y + 1.6, z + 0.5, name, tag="catalog", color="gold")

print("exhibits:", len(exhibits))
b.save(a.name)
