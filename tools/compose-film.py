#!/usr/bin/env python3
"""
Cuts the homepage film from Layers' own phone clips.

  python3 tools/compose-film.py            # write src-video/home-film*.mp4
  python3 tools/build-home-media.py --film # then encode for the web + posters

Almost all of the footage is vertical phone video, so the wide film is a
triptych: three vertical columns side by side, each cycling through its own
clips with soft crossfades, staggered so the columns never change together.
Each column shows phone footage at (close to) its native resolution — nothing
is blown up to fill a 2.33:1 band. Phones get one vertical column.

Every column loops seamlessly: it is rendered as A→B→C→A and the output
window starts after A's fade-in, one full cycle long, so the last frame flows
into the first.

The cut is declared in src-video/film.json:
  "clips":  {name: {"src": "clips/x.mp4", "start": s, "x": 0.5, "grade": {...}}}
  "wide":   {"columns": [[name, name, name], ...], "size": [W, H], "seg": 4.2}
  "narrow": {"sequence": [name, ...], "size": [W, H], "seg": 3.6}
x, y are the centre of the crop (0–1); zoom > 1 punches in. grade keys (all optional):
temp (Kelvin, 6500 = neutral), contrast, saturation, gamma, brightness.
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
VID = ROOT / "src-video"
FADE = 0.7


def run(cmd):
    subprocess.run(cmd, check=True)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:stream_side_data=rotation", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    w, h = s["width"], s["height"]
    rot = next((abs(int(d.get("rotation", 0))) for d in s.get("side_data_list", []) if "rotation" in d), 0)
    return (h, w) if rot in (90, 270) else (w, h)


def grade_filter(g):
    g = g or {}
    f = []
    if g.get("temp"):
        f.append(f"colortemperature=temperature={g['temp']}:mix=0.6:pl=0.5")
    f.append("eq=contrast={c}:saturation={s}:gamma={gm}:brightness={b}".format(
        c=g.get("contrast", 1.04), s=g.get("saturation", 0.94), gm=g.get("gamma", 1.0), b=g.get("brightness", 0.0)))
    # the site's house look: a touch of warmth in the shadows, softened blacks
    f.append("colorbalance=rs=0.02:bs=-0.03:rm=0.01:bm=-0.015")
    f.append("curves=all='0/0.02 0.5/0.5 1/0.985'")
    f.append("hqdn3d=1.2:1.2:4:4")
    return ",".join(f)


def segment(clip, w, h, dur, tmp, name):
    """Trim, crop to w:h around clip['x'], grade, and normalise one clip."""
    src = VID / clip["src"]
    iw, ih = probe(src)
    aspect = w / h
    if iw / ih > aspect:                        # crop the sides
        cw, ch = round(ih * aspect / 2) * 2, ih
    else:                                       # crop top/bottom
        cw, ch = iw, round(iw / aspect / 2) * 2
    z = clip.get("zoom", 1.0)                   # >1 punches in around (x, y)
    cw, ch = round(cw / z / 2) * 2, round(ch / z / 2) * 2
    x = min(max(round(clip.get("x", 0.5) * iw - cw / 2), 0), iw - cw)
    y = min(max(round(clip.get("y", 0.5) * ih - ch / 2), 0), ih - ch)
    speed = clip.get("speed", 1.0)              # <1 slows a clip that is too short
    vf = (f"setpts=PTS/{speed},crop={cw}:{ch}:{x}:{y},scale={w}:{h}:flags=lanczos,{grade_filter(clip.get('grade'))},"
          f"unsharp=5:5:0.35:5:5:0,fps=30,format=yuv420p,setsar=1")
    out = tmp / f"{name}.mp4"
    run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(clip.get("start", 0)), "-t", f"{dur * speed + 0.1:.3f}",
         "-i", str(src), "-an", "-vf", vf, "-t", str(dur), "-c:v", "libx264", "-preset", "medium", "-crf", "12", str(out)])
    return out


def column(names, clips, w, h, seg, offset, tmp, tag):
    """A seamless loop of the named clips; offset (s) staggers its transitions."""
    seq = names + [names[0]]
    parts = [segment(clips[n], w, h, seg, tmp, f"{tag}-{i}-{n}") for i, n in enumerate(seq)]
    fc, last = [], "[0:v]"
    for i in range(1, len(parts)):
        off = i * (seg - FADE)
        fc.append(f"{last}[{i}:v]xfade=transition=fade:duration={FADE}:offset={off:.3f}[x{i}]")
        last = f"[x{i}]"
    cycle = len(names) * (seg - FADE)
    start = FADE + offset                      # inside A, after its fade-in, before B's fade
    out = tmp / f"{tag}.mp4"
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y"]
    for p in parts:
        cmd += ["-i", str(p)]
    cmd += ["-filter_complex", ";".join(fc) + f";{last}trim=start={start:.3f}:duration={cycle:.3f},setpts=PTS-STARTPTS[o]",
            "-map", "[o]", "-c:v", "libx264", "-preset", "medium", "-crf", "12", str(out)]
    run(cmd)
    return out, cycle


def main():
    spec = json.loads((VID / "film.json").read_text())
    clips = spec["clips"]
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        # ---- wide triptych --------------------------------------------------
        wd = spec["wide"]
        W, H = wd["size"]
        cols = wd["columns"]
        cw = W // len(cols) // 2 * 2
        seg = wd.get("seg", 4.2)
        span = seg - 2 * FADE                     # how far a column's start may shift
        outs = []
        for k, names in enumerate(cols):
            off = span * k / max(len(cols) - 1, 1)
            o, cycle = column(names, clips, cw, H, seg, off, tmp, f"col{k}")
            outs.append(o)
        gap = wd.get("gap", 0)
        fc = "".join(f"[{i}:v]" for i in range(len(outs)))
        if gap:
            pads = ";".join(f"[{i}:v]pad=iw+{gap if i < len(outs) - 1 else 0}:ih:0:0:color=0xE5E0D8[p{i}]" for i in range(len(outs)))
            fc = pads + ";" + "".join(f"[p{i}]" for i in range(len(outs)))
        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y"]
        for o in outs:
            cmd += ["-i", str(o)]
        cmd += ["-filter_complex", f"{fc}hstack=inputs={len(outs)}[o]", "-map", "[o]",
                "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-movflags", "+faststart", str(VID / "home-film.mp4")]
        run(cmd)
        print(f"  home-film.mp4    {len(cols)} columns × {cw}x{H}, loop {cycle:.1f}s")
        # ---- narrow (phones) ----------------------------------------------
        nd = spec["narrow"]
        nw, nh = nd["size"]
        o, cycle = column(nd["sequence"], clips, nw, nh, nd.get("seg", 3.6), 0, tmp, "narrow")
        shutil.copy(o, VID / "home-film-m.mp4")
        print(f"  home-film-m.mp4  {nw}x{nh}, loop {cycle:.1f}s")


if __name__ == "__main__":
    if not shutil.which("ffmpeg"):
        sys.exit("error: ffmpeg is required")
    main()
