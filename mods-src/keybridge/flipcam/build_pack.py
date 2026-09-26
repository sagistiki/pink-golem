"""build_pack.py — the resource pack part for Key Bridge's /flipcam (upside-down camera).

The 26.2 client applies the post effect "minecraft:spider" while the camera entity is a spider. This part replaces that
effect with a 180° rotation of the whole image, i.e. the world seen upside down. It uses only vanilla shaders:
  pass 1  post/rotscale (InRotation 180, InScale 1, InOffset 1 → samples at 1 − uv) + post/spiderclip with its
          scissor/vignette pushed outside the screen (so it just copies the rotated image)  main → swap
  pass 2  post/blit  swap → main
Side effect: anyone spectating a real spider (spectator mode) sees the flipped view instead of the vanilla spider view.

    python3 mods-src/keybridge/flipcam/build_pack.py   → mods-src/keybridge/flipcam/flipcam.zip
"""
import json
import os
import zipfile

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flipcam.zip")
PACK_FORMAT = 88  # 26.2 (version.json → pack_version.resource_major)

SPIDER = {
    "targets": {"swap": {}},
    "passes": [
        {
            "vertex_shader": "minecraft:post/rotscale",
            "fragment_shader": "minecraft:post/spiderclip",
            "inputs": [
                {"sampler_name": "In", "target": "minecraft:main"},
                {"sampler_name": "Blur", "target": "minecraft:main"},
            ],
            "output": "swap",
            "uniforms": {
                "RotScaleConfig": [
                    {"name": "InScale", "type": "vec2", "value": [1.0, 1.0]},
                    {"name": "InOffset", "type": "vec2", "value": [1.0, 1.0]},
                    {"name": "InRotation", "type": "float", "value": 180.0},
                ],
                "SpiderConfig": [
                    {"name": "Scissor", "type": "vec4", "value": [-1.0, -1.0, 2.0, 2.0]},
                    {"name": "Vignette", "type": "vec4", "value": [-2.0, -2.0, 3.0, 3.0]},
                ],
            },
        },
        {
            "vertex_shader": "minecraft:core/screenquad",
            "fragment_shader": "minecraft:post/blit",
            "inputs": [{"sampler_name": "In", "target": "swap"}],
            "output": "minecraft:main",
            "uniforms": {"BlitConfig": [{"name": "ColorModulate", "type": "vec4", "value": [1.0, 1.0, 1.0, 1.0]}]},
        },
    ],
}


def main():
    files = {
        "pack.mcmeta": {"pack": {"description": "flip camera: the spider camera effect shows the world upside down",
                                 "min_format": PACK_FORMAT, "max_format": PACK_FORMAT}},
        "assets/minecraft/post_effect/spider.json": SPIDER,
    }
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, json.dumps(data, indent=2) + "\n")
    print(OUT, os.path.getsize(OUT))


if __name__ == "__main__":
    main()
