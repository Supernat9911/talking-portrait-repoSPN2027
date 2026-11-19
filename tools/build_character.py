#!/usr/bin/env python3
"""Build a talking character from a character sheet.

Reads the sheet image, cuts out the pose images (full body, closed mouth) and
the five mouth-shape heads (A, E, I, O, U), aligns every mouth-shape head onto
each pose by template-matching the brows/eyes/nose band, and writes a single
JS file with everything embedded as data URIs, so index.html works when
opened straight from disk (file://) without tainting the WebGL canvas.

Usage:  python3 tools/build_character.py            (builds HUSOC)
Needs:  pip install opencv-python-headless numpy
"""
import base64, json, os, sys
import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# All coordinates are pixels in the source sheet (1672x941).
HUSOC = {
    "id": "husoc",
    "name": "HUSOC",
    "sheet": "characters/husoc/sheet.jpg",
    "out": "characters/husoc.js",
    # pose name -> crop box (x0, y0, x1, y1); poses must face the camera enough
    # for front-facing mouth shapes to fit (the side view is left out).
    "poses": [
        {"id": "front", "name": "หน้าตรง", "box": [360, 0, 670, 475]},
        {"id": "wave", "name": "โบกมือ", "box": [1110, 0, 1420, 475]},
    ],
    # mouth-shape heads: centre x of each column, shared crop height
    "visemes": {"A": 450, "E": 712, "I": 975, "O": 1237, "U": 1498},
    "viseme_crop": {"half_w": 130, "y0": 550, "y1": 850},
    # inside a viseme crop: the band used for alignment and the mouth ellipse
    "align_band": [55, 115, 205, 205],    # x0, y0, x1, y1
    "mouth": {"cx": 130, "cy": 207, "rx": 40, "ry": 30, "feather": 0.35},
    # blink lid size relative to the default (realistic) eye in the shader
    "eye_scale": [1.3, 2.2],
}


def data_uri(img, ext, **kw):
    params = []
    if ext == ".jpg":
        params = [cv2.IMWRITE_JPEG_QUALITY, kw.get("q", 90)]
    ok, buf = cv2.imencode(ext, img, params)
    assert ok
    mime = "image/jpeg" if ext == ".jpg" else "image/png"
    return "data:%s;base64,%s" % (mime, base64.b64encode(buf.tobytes()).decode())


def align(base_gray, tpl_gray):
    best = (-1.0, 1.0, (0, 0))
    for s in np.arange(0.90, 1.40, 0.005):
        t = cv2.resize(tpl_gray, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
        if t.shape[0] >= base_gray.shape[0] or t.shape[1] >= base_gray.shape[1]:
            continue
        r = cv2.matchTemplate(base_gray, t, cv2.TM_CCOEFF_NORMED)
        _, mv, _, ml = cv2.minMaxLoc(r)
        if mv > best[0]:
            best = (mv, float(s), ml)
    return best


def pupils(img, box):
    """Centres of the two darkest blobs (pupils) inside box, sorted left->right."""
    x0, y0, x1, y1 = box
    g = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(g, 45, 255, cv2.THRESH_BINARY_INV)
    n, _, stats, cents = cv2.connectedComponentsWithStats(th)
    blobs = sorted(range(1, n), key=lambda i: -stats[i, cv2.CC_STAT_AREA])[:2]
    pts = sorted((cents[i][0] + x0, cents[i][1] + y0) for i in blobs)
    return pts


def build(cfg):
    sheet = cv2.imread(os.path.join(ROOT, cfg["sheet"]))
    if sheet is None:
        sys.exit("cannot read " + cfg["sheet"])
    vc = cfg["viseme_crop"]
    m = cfg["mouth"]
    bx0, by0, bx1, by1 = cfg["align_band"]
    yy, xx = np.mgrid[0:vc["y1"] - vc["y0"], 0:2 * vc["half_w"]].astype(np.float32)
    d = np.sqrt(((xx - m["cx"]) / m["rx"]) ** 2 + ((yy - m["cy"]) / m["ry"]) ** 2)
    mask = np.clip((1.0 - d) / m["feather"], 0, 1)

    out = {"id": cfg["id"], "name": cfg["name"], "poses": []}
    for pose in cfg["poses"]:
        x0, y0, x1, y1 = pose["box"]
        base = sheet[y0:y1, x0:x1]
        H, W = base.shape[:2]
        bgray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
        mouths = {}
        mouth_pts = []
        for v, cx in cfg["visemes"].items():
            crop = sheet[vc["y0"]:vc["y1"], cx - vc["half_w"]:cx + vc["half_w"]]
            tpl = cv2.cvtColor(crop[by0:by1, bx0:bx1], cv2.COLOR_BGR2GRAY)
            score, s, (lx, ly) = align(bgray, tpl)
            M = np.float32([[s, 0, lx - bx0 * s], [0, s, ly - by0 * s]])
            warped = cv2.warpAffine(crop.astype(np.float32), M, (W, H), flags=cv2.INTER_CUBIC,
                                    borderMode=cv2.BORDER_REPLICATE)
            a = cv2.warpAffine(mask, M, (W, H), flags=cv2.INTER_LINEAR)
            ys, xs = np.nonzero(a > 0.002)
            px0, px1, py0, py1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
            rgba = np.dstack([np.clip(warped, 0, 255), a * 255])[py0:py1, px0:px1]
            mouths[v] = {"src": data_uri(rgba.round().astype(np.uint8), ".png"),
                         "x": int(px0), "y": int(py0)}
            mouth_pts.append(M @ np.float32([m["cx"], m["cy"], 1]))
            print("%-6s %s  match %.3f  scale %.3f" % (pose["id"], v, score, s))
        mc = np.mean(mouth_pts, axis=0)
        # pupils sit in the band between the hood fringe and the nose
        eyes = pupils(base, (0, int(mc[1] - 0.5 * H * 0.3), W, int(mc[1] - 0.04 * H)))
        lm = {"eyeL": [eyes[0][0] / W, eyes[0][1] / H],
              "eyeR": [eyes[1][0] / W, eyes[1][1] / H],
              "mouth": [float(mc[0]) / W, float(mc[1]) / H]}
        print("%-6s landmarks %s" % (pose["id"], json.dumps({k: [round(c, 4) for c in v] for k, v in lm.items()})))
        out["poses"].append({"id": pose["id"], "name": pose["name"], "w": W, "h": H,
                             "base": data_uri(base, ".jpg", q=92), "lm": lm,
                             "eye": cfg["eye_scale"], "mouths": mouths})

    js = ("/* Generated by tools/build_character.py from %s. Do not edit by hand. */\n"
          "window.TP_CHARACTERS=window.TP_CHARACTERS||[];\nwindow.TP_CHARACTERS.push(%s);\n"
          % (cfg["sheet"], json.dumps(out, ensure_ascii=False, separators=(",", ":"))))
    path = os.path.join(ROOT, cfg["out"])
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    print("wrote %s (%.0f KB)" % (cfg["out"], len(js) / 1024))


if __name__ == "__main__":
    build(HUSOC)
