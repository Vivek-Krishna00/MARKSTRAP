"""MarkStrap mark: the Thomas attractor, density-rendered in viridis. Writes web/mark.png and web/favicon.png.

Settings match the original render: b=0.133, x0=(1.1, 1.1, -0.01), dt=0.05, RK4, 800k steps, yaw 45, pitch -34.
Run: .venv/bin/python site/mark.py
"""
import math
import struct
import zlib
from pathlib import Path

import numpy as np

B, DT, STEPS, X0 = 0.133, 0.05, 800_000, (1.1, 1.1, -0.01)
YAW, PITCH, ZOOM = 45, -34, 0.99
SAT_PCT, GAMMA, BLUR = 92, 0.9, 1          # densest 8% of pixels go yellow; blur ~ line width
VIR = np.array([[68, 1, 84], [72, 40, 120], [62, 74, 137], [49, 104, 142], [38, 130, 142], [31, 158, 137],
                [53, 183, 121], [109, 205, 89], [180, 222, 44], [253, 231, 37]]) / 255
BG = np.array([8, 4, 16]) / 255
OUT = Path(__file__).resolve().parent.parent / "web"


def thomas():
    f = lambda x, y, z: (math.sin(y) - B * x, math.sin(z) - B * y, math.sin(x) - B * z)
    x, y, z = X0
    P = np.empty((STEPS, 3))
    for i in range(STEPS):
        k1 = f(x, y, z)
        k2 = f(x + DT / 2 * k1[0], y + DT / 2 * k1[1], z + DT / 2 * k1[2])
        k3 = f(x + DT / 2 * k2[0], y + DT / 2 * k2[1], z + DT / 2 * k2[2])
        k4 = f(x + DT * k3[0], y + DT * k3[1], z + DT * k3[2])
        x += DT / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
        y += DT / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
        z += DT / 6 * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2])
        P[i] = x, y, z
    return P[2000:]                         # drop the transient


def density(P, size, sub=8):
    a, p = math.radians(YAW), math.radians(PITCH)
    x, y, z = P.T
    x, y = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)   # yaw about z
    y, z = y * math.cos(p) - z * math.sin(p), y * math.sin(p) + z * math.cos(p)   # pitch about screen x
    Q = np.stack([x, z], 1)
    t = np.linspace(0, 1, sub, endpoint=False)[None, :, None]                     # lines, not dots
    Q = (Q[:-1, None] + (Q[1:] - Q[:-1])[:, None] * t).reshape(-1, 2)
    Q -= Q.mean(0)
    s = ZOOM * 0.47 * size / np.abs(Q).max()
    ix = np.clip((Q[:, 0] * s + size / 2).astype(int), 0, size - 1)
    iy = np.clip((size / 2 - Q[:, 1] * s).astype(int), 0, size - 1)
    H = np.bincount(iy * size + ix, minlength=size * size).reshape(size, size).astype(float)
    for _ in range(BLUR):
        H = (H + np.roll(H, 1, 0) + np.roll(H, -1, 0) + np.roll(H, 1, 1) + np.roll(H, -1, 1)) / 5
    return H


def colour(H):
    nz = H[H > 0]
    v = np.clip(H / np.percentile(nz, SAT_PCT), 0, 1) ** GAMMA
    c = np.stack([np.interp(v, np.linspace(0, 1, len(VIR)), VIR[:, k]) for k in range(3)], -1)
    a = (np.clip(H / np.percentile(nz, 50), 0, 1) ** 0.6)[..., None]             # faint strands stay, just dark
    return (255 * (BG * (1 - a) + c * a)).astype(np.uint8)


def png(path, img):
    h, w, _ = img.shape
    raw = b"".join(b"\0" + img[r].tobytes() for r in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    P = thomas()
    png(OUT / "mark.png", colour(density(P, 1024)))
    small = density(P, 192).reshape(64, 3, 64, 3).sum((1, 3))                      # coarse density = thick strokes at 16-32px
    png(OUT / "favicon.png", colour(small))
    print("wrote", OUT / "mark.png", OUT / "favicon.png")
