#!/usr/bin/env python3
"""Board Game Porter: turn photos or scans of a real board game into a
Tabletop Club asset pack.

    python3 porter.py MY_GAME_FOLDER            # builds MY_GAME_FOLDER/_pack
    python3 porter.py MY_GAME_FOLDER --install  # also copies it into
                                                # ~/Documents/TabletopClub/assets

Input folder layout (everything is optional):

    MY_GAME_FOLDER/
      porter.toml           sizes, card sheets, names (see example.toml)
      board.jpg             the board, any image type
      cards/<Deck name>/    one image per card front, plus back.jpg
      tokens/round/         round tokens (chips, coins, markers)
      tokens/square/        square tiles or tokens
      backs/                optional back images, same file name as the front

Photos can be taken on a plain table: each one is cropped to the piece and
straightened automatically. Needs Python 3.11+, Pillow and numpy.
"""

from __future__ import annotations

import argparse
import math
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic"}
CARD_PX = 750       # long side of card images
TOKEN_PX = 1024     # token texture size
BOARD_PX = 4096     # long side of the board image
DEFAULT_CARD_CM = (6.35, 8.89)


# ---------------------------------------------------------------- images ---

def load(path: Path) -> Image.Image:
    if path.suffix.lower() == ".heic":  # iPhone photos: let macOS convert them
        tmp = Path(tempfile.mkdtemp()) / (path.stem + ".png")
        subprocess.run(["sips", "-s", "format", "png", str(path), "--out", str(tmp)],
                       check=True, capture_output=True)
        path = tmp
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)  # phone photos come in sideways
    return img.convert("RGB")


def images_in(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir()
                  if p.suffix.lower() in IMAGE_TYPES and not p.name.startswith("."))


def _mask(img: Image.Image, size: int = 400) -> tuple[np.ndarray, float]:
    """True where the piece is, False where the table/background is."""
    small = img.copy()
    small.thumbnail((size, size))
    a = np.asarray(small, dtype=np.float32)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    spread = np.median(np.abs(border - bg)) + 1
    dist = np.sqrt(((a - bg) ** 2).sum(axis=2))
    return dist > max(40.0, 6 * spread), img.width / small.width


def _bbox_area(mask: np.ndarray, angle: float) -> float:
    ys, xs = np.nonzero(mask)
    t = math.radians(angle)
    rx = xs * math.cos(t) - ys * math.sin(t)
    ry = xs * math.sin(t) + ys * math.cos(t)
    return (np.percentile(rx, 99.5) - np.percentile(rx, 0.5)) * \
           (np.percentile(ry, 99.5) - np.percentile(ry, 0.5))


def auto_crop(img: Image.Image, enabled: bool = True) -> Image.Image:
    """Crop a photo to the piece and straighten small tilts (up to 20 deg).

    Scans and already-clean images (piece fills the frame) pass through."""
    if not enabled:
        return img
    mask, scale = _mask(img)
    if mask.mean() < 0.02 or mask.mean() > 0.97:
        return img  # nothing found, or the piece already fills the picture
    best = min((a / 2 for a in range(-40, 41)), key=lambda a: _bbox_area(mask, a))
    # round pieces look the same at every angle: only turn when it really helps
    if abs(best) >= 0.5 and _bbox_area(mask, best) < 0.97 * _bbox_area(mask, 0):
        img = img.rotate(-best, resample=Image.BICUBIC, expand=True,
                         fillcolor=tuple(int(c) for c in np.asarray(img)[0, 0]))
        mask, scale = _mask(img)
    ys, xs = np.nonzero(mask)
    box = [np.percentile(xs, 0.5), np.percentile(ys, 0.5),
           np.percentile(xs, 99.5) + 1, np.percentile(ys, 99.5) + 1]
    box = [int(round(v * scale)) for v in box]
    # trim a hair inside so no table colour shows on the edge
    pad = int(0.006 * max(box[2] - box[0], box[3] - box[1]))
    return img.crop((box[0] + pad, box[1] + pad, box[2] - pad, box[3] - pad))


def fit(img: Image.Image, long_side: int) -> Image.Image:
    img = img.copy()
    if max(img.size) > long_side:
        img.thumbnail((long_side, long_side), Image.LANCZOS)
    return img


def edge_colour(img: Image.Image) -> tuple[int, int, int]:
    a = np.asarray(img)
    ring = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    return tuple(int(c) for c in np.median(ring, axis=0))


def split_sheet(img: Image.Image, rows: int, cols: int, count: int | None,
                margin: float = 0.0) -> list[Image.Image]:
    """Cut a sheet of cards (a scan or print-and-play page) into cards."""
    w, h = img.size
    mx, my = int(w * margin), int(h * margin)
    cw, ch = (w - 2 * mx) / cols, (h - 2 * my) / rows
    out = []
    for r in range(rows):
        for c in range(cols):
            if count is not None and len(out) >= count:
                return out
            out.append(img.crop((int(mx + c * cw), int(my + r * ch),
                                 int(mx + (c + 1) * cw), int(my + (r + 1) * ch))))
    return out


# ------------------------------------------------------------ textures ---

def cylinder_texture(front: Image.Image, back: Image.Image | None) -> Image.Image:
    """Tabletop Club cylinder UV: top half = side, bottom-left = top circle,
    bottom-right = bottom circle."""
    s = TOKEN_PX
    # side colour: a ring just inside the rim (the corners are table, not token)
    a = np.asarray(front.resize((200, 200)))
    yy, xx = np.mgrid[:200, :200]
    r = np.hypot(xx - 99.5, yy - 99.5)
    rim = tuple(int(c) for c in np.median(a[(r > 85) & (r < 95)], axis=0))
    tex = Image.new("RGB", (s, s), rim)
    for img, x in ((front, 0), (back or front, s // 2)):
        side = min(img.size)
        sq = img.crop(((img.width - side) // 2, (img.height - side) // 2,
                       (img.width + side) // 2, (img.height + side) // 2))
        tex.paste(sq.resize((s // 2, s // 2), Image.LANCZOS), (x, s // 2))
    return tex


def cube_texture(front: Image.Image, back: Image.Image | None) -> Image.Image:
    """Tabletop Club cube UV, 3 x 2 grid:
    Back Left Front / Right Top Bottom. The picture goes on Top."""
    cw, ch = TOKEN_PX // 3, TOKEN_PX // 2
    tex = Image.new("RGB", (cw * 3, ch * 2), edge_colour(front))
    tex.paste(front.resize((cw, ch), Image.LANCZOS), (cw, ch))
    tex.paste((back or front).resize((cw, ch), Image.LANCZOS), (cw * 2, ch))
    return tex


# --------------------------------------------------------------- board ---

def write_board(out: Path, name: str, img: Image.Image, width_cm: float,
                thickness_cm: float) -> None:
    """A flat box whose top shows the board picture."""
    img = fit(img, BOARD_PX)
    tex_name, side_name = f"{name}.jpg", f"{name} edge.png"
    img.save(out / tex_name, quality=92)
    Image.new("RGB", (8, 8), edge_colour(img)).save(out / side_name)

    w = width_cm / 2
    d = width_cm * img.height / img.width / 2
    t = thickness_cm
    # Y is up. Top face corners first, then bottom.
    v = [(-w, t, -d), (w, t, -d), (w, t, d), (-w, t, d),
         (-w, 0, -d), (w, 0, -d), (w, 0, d), (-w, 0, d)]
    lines = [f"mtllib {name}.mtl", f"o {name}"]
    lines += [f"v {x:.4f} {y:.4f} {z:.4f}" for x, y, z in v]
    # image top-left sits at the far-left corner (-w, -d)
    lines += ["vt 0 1", "vt 1 1", "vt 1 0", "vt 0 0"]
    lines += ["vn 0 1 0", "vn 0 -1 0", "vn 0 0 -1", "vn 1 0 0", "vn 0 0 1", "vn -1 0 0"]
    lines += ["usemtl Top", "f 1/1/1 4/4/1 3/3/1 2/2/1", "usemtl Edge",
              "f 5/1/2 6/2/2 7/3/2 8/4/2",          # bottom
              "f 1/1/3 2/2/3 6/3/3 5/4/3",          # back
              "f 2/1/4 3/2/4 7/3/4 6/4/4",          # right
              "f 3/1/5 4/2/5 8/3/5 7/4/5",          # front
              "f 4/1/6 1/2/6 5/3/6 8/4/6"]          # left
    (out / f"{name}.obj").write_text("\n".join(lines) + "\n")
    (out / f"{name}.mtl").write_text(
        "newmtl Top\nKd 1 1 1\nmap_Kd {}\n\nnewmtl Edge\nKd 1 1 1\nmap_Kd {}\n"
        .format(tex_name, side_name))


# -------------------------------------------------------------- config ---

def cfg_str(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "-", name).strip() or "piece"


def write_cfg(folder: Path, sections: dict[str, dict]) -> None:
    lines = ["; Made by Board Game Porter. Personal copy - do not share",
             "; images you do not have the rights to.", ""]
    for section, keys in sections.items():
        lines.append(f"[{section}]")
        for k, val in keys.items():
            lines.append(f"{k} = {val}")
        lines.append("")
    (folder / "config.cfg").write_text("\n".join(lines))


# --------------------------------------------------------------- build ---

def find_back(src: Path, front: Path) -> Path | None:
    for p in images_in(src / "backs"):
        if p.stem == front.stem:
            return p
    return None


def build(src: Path, out: Path, conf: dict) -> list[str]:
    report = []
    crop = conf.get("auto_crop", True)
    game = conf.get("name", src.name)
    author = conf.get("author", "Scanned from my own copy")
    if out.exists():
        shutil.rmtree(out)

    # Board ------------------------------------------------------------
    board_conf = conf.get("board", {})
    board_img = src / board_conf["image"] if "image" in board_conf else \
        next((p for p in images_in(src) if p.stem.lower() == "board"), None)
    if board_img:
        folder = out / "boards"
        folder.mkdir(parents=True)
        name = safe(f"{game} Board")
        img = auto_crop(load(board_img), board_conf.get("auto_crop", crop))
        width = float(board_conf.get("width_cm", 50))
        write_board(folder, name, img, width, float(board_conf.get("thickness_cm", 0.4)))
        write_cfg(folder, {
            f"{name}.obj": {"name": cfg_str(f"{game} board"), "author": cfg_str(author),
                            "mass": 800.0, "sfx": cfg_str("wood_heavy")},
        })  # the board's pictures must NOT be ignored: the model loads them
        report.append(f"board: {width:g} cm wide")

    # Cards ------------------------------------------------------------
    decks = {d["name"]: d for d in conf.get("decks", [])}
    for sub in sorted(p for p in (src / "cards").glob("*") if p.is_dir()):
        decks.setdefault(sub.name, {"name": sub.name})
    if images_in(src / "cards"):
        decks.setdefault("Cards", {"name": "Cards", "folder": "cards"})
    card_dir = out / "cards"
    card_sections: dict[str, dict] = {}
    for deck in decks.values():
        dname = safe(deck["name"])
        dsrc = src / deck.get("folder", f"cards/{deck['name']}")
        w_cm, h_cm = deck.get("width_cm"), deck.get("height_cm")
        fronts: list[tuple[str, Image.Image]] = []
        back_img = None
        if "sheet" in deck:
            # sheets are usually scans or PDF pages, so no auto crop unless asked
            sheet = auto_crop(load(src / deck["sheet"]), deck.get("auto_crop", False))
            parts = split_sheet(sheet, int(deck.get("rows", 3)), int(deck.get("cols", 3)),
                                deck.get("count"), float(deck.get("margin", 0)))
            names = deck.get("names", [])
            fronts = [(names[i] if i < len(names) else f"{deck['name']} {i + 1}", p)
                      for i, p in enumerate(parts)]
        for p in images_in(dsrc):
            if p.stem.lower() == "back":
                back_img = auto_crop(load(p), crop)
            else:
                fronts.append((p.stem, auto_crop(load(p), crop)))
        if "back" in deck:
            back_img = auto_crop(load(src / deck["back"]), crop)
        if not fronts:
            continue
        if not (w_cm and h_cm):
            # keep the real shape: poker width, height from the picture
            fw, fh = fronts[0][1].size
            w_cm = DEFAULT_CARD_CM[0]
            h_cm = round(w_cm * fh / fw, 2)
        card_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"{dname} - "
        back_file = f"{prefix}back.png"
        if back_img is None:  # plain back in the card's edge colour
            back_img = Image.new("RGB", fronts[0][1].size, edge_colour(fronts[0][1]))
        fit(back_img, CARD_PX).save(card_dir / back_file)
        card_sections[f"{prefix}*"] = {"scale": f"Vector2({w_cm}, {h_cm})",
                                       "back_face": cfg_str(back_file),
                                       "author": cfg_str(author), "mass": 1.8}
        card_sections[back_file] = {"ignore": "true"}
        for i, (label, img) in enumerate(fronts):
            file = f"{prefix}{i + 1:03d}.png"
            fit(img, CARD_PX).save(card_dir / file)
            card_sections[file] = {"name": cfg_str(label)}
        report.append(f"deck '{deck['name']}': {len(fronts)} cards, {w_cm} x {h_cm} cm")
    if card_sections:
        write_cfg(card_dir, card_sections)

    # Tokens -----------------------------------------------------------
    tok = conf.get("tokens", {})
    for shape, kind, maker in (("round", "cylinder", cylinder_texture),
                               ("square", "cube", cube_texture)):
        files = images_in(src / "tokens" / shape)
        if not files:
            continue
        t = tok.get(shape, {})
        size = float(t.get("size_cm", 2.5))
        thick = float(t.get("thickness_cm", 0.3))
        folder = out / "tokens" / kind
        folder.mkdir(parents=True)
        sections = {"*": {"scale": f"Vector3({size}, {thick}, {size})",
                          "author": cfg_str(author), "mass": 2.0}}
        for p in files:
            front = auto_crop(load(p), crop)
            b = find_back(src, p)
            back = auto_crop(load(b), crop) if b else None
            file = f"{safe(p.stem)}.png"
            maker(front, back).save(folder / file)
            sections[file] = {"name": cfg_str(p.stem)}
        write_cfg(folder, sections)
        report.append(f"{shape} tokens: {len(files)}, {size} cm")

    if not report:
        raise SystemExit(f"Nothing found in {src}. See the layout at the top of porter.py.")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("game", type=Path, help="folder with your photos")
    ap.add_argument("--out", type=Path, help="where to write the pack (default GAME/_pack)")
    ap.add_argument("--install", action="store_true",
                    help="copy the pack into ~/Documents/TabletopClub/assets")
    args = ap.parse_args()
    src = args.game.expanduser().resolve()
    conf_file = src / "porter.toml"
    conf = tomllib.loads(conf_file.read_text()) if conf_file.exists() else {}
    out = (args.out or src / "_pack").expanduser().resolve()
    for line in build(src, out, conf):
        print("  " + line)
    print(f"Pack written to {out}")
    if args.install:
        dest = Path.home() / "Documents/TabletopClub/assets" / safe(conf.get("name", src.name))
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(out, dest)
        print(f"Installed to {dest} - restart Tabletop Club (or use Import Assets).")


if __name__ == "__main__":
    sys.exit(main())
