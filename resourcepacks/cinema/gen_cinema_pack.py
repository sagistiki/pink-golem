"""gen_cinema_pack.py — builds the cinema resource-pack part and films.json from the film modules in this folder.

For every entry in FILMS: render all played frames, dedupe identical ones into unique `cinema:<id>_fNNNN` quad
models (16:9 element, 256x144 palette PNG textures), render the score to Ogg and register it in sounds.json, draw
the posters, and write review material (a contact sheet of every 4th frame + all cards, a poster sheet, a model
preview PNG).

    python3 gen_cinema_pack.py
        -> resourcepacks/cinema/build/ + resourcepacks/cinema/cinema.zip
           scarpet-apps/cinema.data.example/films.json   (the working example — copy the whole
                                                            cinema.data.example/ folder to your world as cinema.data/)
           resourcepacks/cinema/preview_*.png

Adding a film = one more film_<id>.py + music_<id>.py in this folder (see film_demo.py / music_demo.py for the
module contract) and one more entry in FILMS below. This script never touches a running server — add the resulting
cinema.zip to your resource-pack build (`minecraft_pack build` / your own merge step) and copy
cinema.data.example/*.json into your world's `scripts/cinema.data/`.

See skill/pinkgolem/reference/cinema-and-gallery.md for the full walkthrough (the room/seat/button setup, the yaw
convention, the numbers behind "why item-model frames" instead of map art or a block wall).
"""
import importlib
import json
import math
import os
import subprocess
import sys
import time

import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import cinemalib as cl  # noqa: E402

NS = "cinema"
OUT = os.path.join(HERE, "build")
ZIP = os.path.join(HERE, "cinema.zip")
FILMS_JSON = os.path.join(ROOT, "scarpet-apps", "cinema.data.example", "films.json")

# Films to build: the film module name; its FILM["music"] names the music module. Order = order in the cinema dialog.
FILMS = ["film_demo"]

# Screen quad: 16 wide x 9 tall, vertically centred (element y 3.5..12.5) — a room scales this with `screen.scale`
# in rooms.json (see cinema-and-gallery.md for what scale to use for a given wall size).
SCREEN_Y0, SCREEN_Y1 = 3.5, 12.5


def build_film(pack, modname, sheets_dir):
    film = importlib.import_module(modname)
    meta = film.FILM
    fid = meta["id"]
    t0 = time.time()

    # -- frames -> unique models --------------------------------------------------------------------------------------
    store = cl.FrameStore(fid)
    frames = []
    for i in range(meta["frames"]):
        fr = film.render_frame(i)
        frames.append(fr)
        store.add(fr)
    for mid, im in store.images.items():
        pack.quad(mid, im, SCREEN_Y0, SCREEN_Y1)
    sizes = [pack.sizes[m] for m in store.images]
    print(f"[{fid}] {meta['frames']} frames -> {store.unique} unique models in {time.time() - t0:.1f}s; "
          f"png avg {sum(sizes) / len(sizes) / 1024:.1f} KB, max {max(sizes) / 1024:.1f} KB")

    # -- posters ---------------------------------------------------------------------------------------------------
    for pname, fn in film.POSTERS.items():
        pack.quad(pname, fn())

    # -- music: rendered straight into the pack's sounds folder, then read back to verify (mono, peak headroom) ---
    music = importlib.import_module(meta["music"])
    ogg = pack.sound_path(f"{fid}_theme")
    music.render(ogg)
    sound_id = pack.sound(f"{fid}_theme", ogg)
    data, sr = sf.read(ogg)
    ogg_s = len(data) / sr
    channels = 1 if data.ndim == 1 else data.shape[1]
    peak_db = 20 * math.log10(max(1e-9, float(abs(data).max())))
    print(f"[{fid}] ogg {ogg_s:.2f}s @ {sr} Hz, {channels} channel(s), peak {peak_db:.2f} dBFS, "
          f"{os.path.getsize(ogg) / 1024:.0f} KB")
    assert channels == 1, "music must be mono — a stereo 'record' sound is not positional in Minecraft"
    assert abs(ogg_s - meta["music_s"]) < 1.0 and peak_db <= -1.0, "score length/peak out of spec"

    # -- review material -------------------------------------------------------------------------------------------
    card_first = {a: text for a, b, text in film.CARDS}
    idx = sorted(set(range(0, meta["frames"], 4)) | set(card_first))
    labels = [f"f{i}  {i / meta['fps']:.2f}s" + ("  [card]" if i in card_first else "") for i in idx]
    cl.contact_sheet([frames[i] for i in idx], labels, cols=7).save(os.path.join(sheets_dir, f"preview_{fid}_sheet.png"))
    poster_prev = cl.contact_sheet([film.POSTERS[p]() for p in film.POSTERS], list(film.POSTERS), cols=2, scale=2)
    poster_prev.save(os.path.join(sheets_dir, "preview_poster.png"))

    assert f"poster_{fid}" in film.POSTERS, f"{modname}.POSTERS must contain poster_{fid}"
    # cards: "to" is inclusive; texts are LOGICAL order (Minecraft, and cinemalib.card(), do their own bidi/visual reorder)
    return {"id": fid, "title": meta["title"], "en": meta.get("en", meta["title"]), "year": meta["year"], "fps": meta["fps"],
            "frame_models": [f"{NS}:{m}" for m in store.sequence],
            "cards": [{"from": a, "to": b, "text": text} for a, b, text in film.CARDS],
            "music": sound_id, "music_s": meta["music_s"], "poster": f"{NS}:poster_{fid}"}, store.unique


def main():
    pack = cl.Pack(OUT, NS, "Demo cinema films (Pink Golem cinema-and-gallery example)")
    pack.quad("black", cl.black_frame(), SCREEN_Y0, SCREEN_Y1)
    films, uniques = [], {}
    for modname in FILMS:
        entry, n = build_film(pack, modname, HERE)
        films.append(entry)
        uniques[entry["id"]] = n
    os.makedirs(os.path.dirname(FILMS_JSON), exist_ok=True)
    with open(FILMS_JSON, "w", encoding="utf-8") as f:
        json.dump(films, f, ensure_ascii=False, indent=1)
    size = pack.write(ZIP)
    print(f"pack {ZIP}: {size / 1024 / 1024:.2f} MB ({size} bytes); films.json -> {FILMS_JSON}")
    # model preview of one mid-film frame
    first = films[0]["id"]
    mid = f"{NS}:item/{first}_f{min(20, uniques[first]):04d}"
    prev = os.path.join(HERE, "preview_model.png")
    preview_tool = os.path.join(ROOT, "resourcepacks", "tools", "model_preview.py")
    subprocess.run([sys.executable, preview_tool, OUT, mid, "--out", prev, "--yaw", "25", "--pitch", "12"], check=False)
    print(json.dumps({"zip": ZIP, "zip_mb": round(size / 1048576, 2), "unique_frames": uniques, "model_preview": prev}))


if __name__ == "__main__":
    main()
