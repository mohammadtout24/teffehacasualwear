"""Draws flat garment illustrations used as placeholder product photos.

Only the sample-data command uses this. Real product photos uploaded in the
admin replace these images entirely.
"""

import io
import math
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

W, H = 900, 1200          # output size (3:4 portrait, like fashion product shots)
S = 2                     # supersampling factor for smooth edges
CX, NY, WY = 450, 250, 230  # centre x, top-garment neck y, bottoms waist y


# --- colour helpers ----------------------------------------------------------

def rgb(hex_code):
    h = hex_code.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def darker(c, t):
    return mix(c, (20, 10, 12), t)


def lighter(c, t):
    return mix(c, (255, 255, 255), t)


def lum(c):
    return (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255


# --- geometry helpers --------------------------------------------------------

def P(pts):
    return [(x * S, y * S) for x, y in pts]


def mirror(pts):
    """Reflect a left-half path across the centre line (and reverse it)."""
    return [(2 * CX - x, y) for x, y in reversed(pts)]


def arc(cx, cy, rx, ry, a0, a1, n=28):
    return [
        (cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
         cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
        for i in range(n + 1)
    ]


def bez(*ctrl, n=24):
    pts = []
    for i in range(n + 1):
        t = i / n
        p = list(ctrl)
        while len(p) > 1:
            p = [((1 - t) * a[0] + t * b[0], (1 - t) * a[1] + t * b[1]) for a, b in zip(p, p[1:])]
        pts.append(p[0])
    return pts


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def offset_toward(a, b, dist):
    """Point `dist` px from a toward b."""
    length = math.hypot(b[0] - a[0], b[1] - a[1]) or 1
    return lerp(a, b, dist / length)


def full_outline(left, neck_front=None):
    """left: path from the top-left point down to a point on the centre line.
    neck_front: path from the top-right point back to the top-left one."""
    right = mirror(left)[1:]
    pts = left + right
    if neck_front:
        pts += neck_front[1:-1]
    return pts


# --- drawing -----------------------------------------------------------------

class Pen:
    def __init__(self, color, accent=None):
        self.img = Image.new('RGBA', (W * S, H * S), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.c = color
        dark = lum(color) < 0.25
        self.line = lighter(color, .32) if dark else darker(color, .34)
        self.inner = lighter(color, .10) if dark else darker(color, .20)
        self.band = lighter(color, .05) if dark else darker(color, .09)
        self.accent = accent or self.line
        self.metal = (192, 188, 182) if dark else (150, 140, 128)
        self.highlights = []   # (cx, cy, rx, ry, strength) soft light spots

    def fill(self, pts, color=None, outline=True, w=2.6):
        self.d.polygon(P(pts), fill=color or self.c)
        if outline:
            self.stroke(pts, w=w, closed=True)

    def stroke(self, pts, w=2.6, color=None, closed=False):
        pts = list(pts) + ([pts[0]] if closed else [])
        self.d.line(P(pts), fill=color or self.line, width=max(1, int(w * S)), joint='curve')

    def dashed(self, pts, w=2, dash=11, gap=8, color=None):
        color = color or self.accent
        drawing, remaining = True, dash
        for a, b in zip(pts, pts[1:]):
            seg = math.hypot(b[0] - a[0], b[1] - a[1])
            pos = 0
            while pos < seg:
                step = min(remaining, seg - pos)
                if drawing:
                    self.stroke([lerp(a, b, pos / seg), lerp(a, b, (pos + step) / seg)], w=w, color=color)
                pos += step
                remaining -= step
                if remaining <= 0:
                    drawing = not drawing
                    remaining = dash if drawing else gap

    def dot(self, x, y, r, color=None, outline=None):
        self.d.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S],
                       fill=color or self.line, outline=outline, width=S)

    def button(self, x, y, r=8, color=None):
        color = color or (lighter(self.c, .45) if lum(self.c) < .5 else darker(self.c, .45))
        self.dot(x, y, r, color=color, outline=self.line)
        self.dot(x - r * .3, y, 1.4, color=self.line)
        self.dot(x + r * .3, y, 1.4, color=self.line)

    def texture(self, clip_pts, spacing=14, angle=90, color=None, w=1.2, box=None):
        """Parallel lines (ribbing, twill, smocking) clipped to a polygon."""
        layer = Image.new('RGBA', self.img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        color = (color or self.band) + (255,)
        rad = math.radians(angle)
        dx, dy = math.cos(rad), math.sin(rad)
        span = int(math.hypot(W, H))
        for k in range(-span, span, spacing):
            ox, oy = CX + k * -dy, H / 2 + k * dx
            a = (ox - dx * span, oy - dy * span)
            b = (ox + dx * span, oy + dy * span)
            ld.line(P([a, b]), fill=color, width=max(1, int(w * S)))
        mask = Image.new('L', self.img.size, 0)
        ImageDraw.Draw(mask).polygon(P(clip_pts), fill=255)
        if box:
            bmask = Image.new('L', self.img.size, 0)
            ImageDraw.Draw(bmask).rectangle([v * S for v in box], fill=255)
            mask = ImageChops.multiply(mask, bmask)
        layer.putalpha(ImageChops.multiply(layer.getchannel('A'), mask))
        self.img.alpha_composite(layer)

    def apple(self, x, y, s=16, color=None):
        """Tiny apple mark — 'teffaha' means apple."""
        color = color or self.accent
        self.dot(x - s * .26, y, s * .42, color=color)
        self.dot(x + s * .26, y, s * .42, color=color)
        self.dot(x, y + s * .18, s * .40, color=color)
        self.stroke([(x, y - s * .3), (x + s * .08, y - s * .62)], w=s * .12, color=color)
        leaf = bez((x + s * .1, y - s * .5), (x + s * .4, y - s * .85), (x + s * .62, y - s * .55), n=8) + \
            bez((x + s * .62, y - s * .55), (x + s * .38, y - s * .38), (x + s * .1, y - s * .5), n=8)
        self.d.polygon(P(leaf), fill=color)


# --- shared silhouettes ------------------------------------------------------

def top_left(sleeve='short', nw=66, sw=196, bw=158, hem=880, hem_w=None, drop=32,
             waist_in=0, sleeve_len=None, curve=8, strap=40, armhole_y=None):
    """Left half of a top: neck point -> shoulder/sleeve -> side -> hem centre."""
    hem_w = hem_w or bw + 6
    neck = (CX - nw, NY)
    pts, a = [neck], {'neck': neck}
    if sleeve == 'none':
        so = (CX - nw - strap, NY + 2)
        ay = armhole_y or NY + 200
        armpit = (CX - bw, ay)
        pts += [so] + bez(so, (CX - nw - strap - 4, NY + 110), (CX - bw + 34, ay - 6), armpit, n=18)[1:]
        a.update(shoulder=so, armpit=armpit)
    else:
        shoulder = (CX - sw, NY + drop)
        pts.append(shoulder)
        if sleeve == 'short':
            length = sleeve_len or 170
            co = (CX - sw - 88, NY + drop + length - 30)
            ci = (CX - bw - 62, NY + drop + length + 10)
            armpit = (CX - bw, NY + 170)
        elif sleeve == 'long':
            length = sleeve_len or 560
            co = (CX - sw - 92, NY + length)
            ci = (CX - sw - 30, NY + length + 14)
            armpit = (CX - bw, NY + 200)
        else:  # puff
            co = (CX - sw - 52, NY + 190)
            ci = (CX - bw - 30, NY + 208)
            armpit = (CX - bw, NY + 178)
            pts += bez(shoulder, (CX - sw - 80, NY + 10), (CX - sw - 118, NY + 150), co, n=22)[1:-1]
        pts += [co, ci, armpit]
        a.update(shoulder=shoulder, cuff_o=co, cuff_i=ci, armpit=armpit)
    if waist_in:
        pts.append((CX - bw + waist_in, a['armpit'][1] + (hem - a['armpit'][1]) * .5))
    hc = (CX - hem_w, hem - curve)
    pts += bez(hc, (CX - hem_w * .45, hem + 1), (CX, hem), n=12)
    a.update(hem_corner=hc, hem=hem, hem_w=hem_w, bw=bw, nw=nw)
    return pts, a


def crew(nw, depth):
    return arc(CX, NY, nw, depth, 0, 180)


def back_neck(pen, front, nw, dip=10, color=None):
    back = arc(CX, NY, nw, dip, 180, 0)
    pen.fill(back + front[1:-1], color=color or pen.inner)


def neck_band(pen, nw, depth, width=12):
    outer = arc(CX, NY, nw, depth, 0, 180)
    inner = arc(CX, NY, nw + width * .8, depth + width, 180, 0)
    pen.fill(outer + inner, color=pen.band)


def armhole_seams(pen, a):
    for side in (1, -1):
        s, ap = a['shoulder'], a['armpit']
        pts = bez(s, (s[0] + 12, s[1] + 70), (ap[0] - 6, ap[1] - 50), ap, n=14)
        pen.stroke(pts if side == 1 else [(2 * CX - x, y) for x, y in pts], w=2)


def sleeve_bands(pen, a, depth=22, rib=False):
    """Cuff: a ribbed band when `rib`, otherwise just a hem stitch line."""
    co, ci = a['cuff_o'], a['cuff_i']
    top_o = offset_toward(co, a['shoulder'], depth)
    top_i = offset_toward(ci, a['armpit'], depth)
    along = math.degrees(math.atan2(ci[1] - top_i[1], ci[0] - top_i[0]))
    for flip in (False, True):
        pts = [co, ci, top_i, top_o]
        if flip:
            pts = [(2 * CX - x, y) for x, y in pts]
        if rib:
            pen.fill(pts, color=pen.band)
            pen.texture(pts, spacing=9, angle=180 - along if flip else along, color=pen.line, w=1)
            pen.stroke(pts, closed=True, w=2)
        else:
            pen.stroke([pts[3], pts[2]], w=1.6)


def hem_band(pen, a, height=50, rib=True):
    hw, hem = a['hem_w'], a['hem']
    pts = [(CX - hw, hem - height), (CX + hw, hem - height)] + \
        bez((CX + hw, hem - 8), (CX + hw * .45, hem + 1), (CX, hem), n=8) + \
        bez((CX, hem), (CX - hw * .45, hem + 1), (CX - hw, hem - 8), n=8)[1:]
    pen.fill(pts, color=pen.band if rib else pen.c)
    if rib:
        pen.texture(pts, spacing=9, angle=90, color=pen.line, w=1)
        pen.stroke(pts, closed=True, w=2)


def hem_stitch(pen, a, offset=22):
    hw, hem = a['hem_w'] - 4, a['hem'] - offset
    pen.stroke(bez((CX - hw, hem - 7), (CX - hw * .45, hem + 1), (CX + hw * .45, hem + 1), (CX + hw, hem - 7), n=16), w=1.6)


def collar(pen, nw, spread=30, length=92, rounded=False):
    stand = arc(CX, NY - 2, nw + 6, 22, 180, 360)
    pen.fill(stand + list(reversed(arc(CX, NY, nw, 6, 180, 360))), color=pen.band)
    left = [(CX - nw - 6, NY - 6), (CX - 3, NY + 26), (CX - 20, NY + length), (CX - nw - spread, NY + 44)]
    if rounded:
        left = [(CX - nw - 6, NY - 6), (CX - 3, NY + 22)] + bez((CX - 3, NY + 22), (CX - 10, NY + length), (CX - 40, NY + length), n=8)[1:] + [(CX - nw - spread, NY + 40)]
    for pts in (left, [(2 * CX - x, y) for x, y in left]):
        pen.fill(pts)


def hood(pen, width=150, top=105, inner=True):
    left = [(CX - width, NY + 50)] + bez((CX - width, NY + 50), (CX - width - 18, NY - 50), (CX - 110, NY - top), (CX, NY - top), n=20)[1:]
    pts = left + mirror(left)[1:]
    pen.fill(pts)
    pen.stroke(bez((CX - 30, NY - top + 4), (CX, NY - top + 20), (CX + 30, NY - top + 4), n=8), w=1.5)
    if inner:
        pen.fill(arc(CX, NY + 6, width - 42, 80, 0, 360), color=pen.inner)


# --- garments: tops ----------------------------------------------------------

def tee(pen, oversized=False, length=880, dress=False, sport=False, men=False):
    kw = dict(sleeve='short', nw=66, sw=196, bw=158, hem=length)
    if oversized:
        kw.update(sw=226, bw=184, drop=50, sleeve_len=190, hem=length + 20)
    if men:
        kw.update(sw=212, bw=176, nw=64, hem=length + 20)
    if dress:
        kw.update(hem=1070, hem_w=212, waist_in=6)
    left, a = top_left(**kw)
    front = crew(a['nw'], 48)
    pen.fill(full_outline(left, front))
    back_neck(pen, front, a['nw'])
    if sport:
        for flip in (False, True):
            pts = [a['neck'], a['shoulder'], a['cuff_o'], a['cuff_i'], a['armpit'], (CX - a['nw'] + 12, NY + 20)]
            if flip:
                pts = [(2 * CX - x, y) for x, y in pts]
            pen.fill(pts, color=pen.band, outline=False)
            pen.stroke([pts[-1], pts[4]], w=2)
        for side in (-1, 1):
            x = CX + side * (a['bw'] - 22)
            pen.dashed([(x, a['armpit'][1] + 40), (x + side * 4, a['hem'] - 40)], w=1.6, dash=6, gap=6, color=pen.line)
        pen.apple(CX + 70, NY + 105, 15, color=pen.accent)
    else:
        armhole_seams(pen, a)
    neck_band(pen, a['nw'], 48)
    sleeve_bands(pen, a, depth=22)
    hem_stitch(pen, a)
    return a


def shirt(pen, pocket=False, denim=False, oversized=False):
    kw = dict(sleeve='long', nw=56, sw=202, bw=166, hem=900, curve=48)
    if oversized:
        kw.update(sw=228, bw=186, drop=46, hem=920)
    left, a = top_left(**kw)
    front = crew(56, 34)
    pen.fill(full_outline(left, front))
    back_neck(pen, front, 56)
    armhole_seams(pen, a)
    stitch = pen.accent if denim else pen.line
    for x in (CX - 16, CX + 16):
        pen.stroke([(x, NY + 30), (x, a['hem'] - 2)], w=1.6)
    y = NY + 70
    while y < a['hem'] - 40:
        pen.button(CX, y, 7)
        y += 88
    sleeve_bands(pen, a, depth=60)
    for flip in (False, True):
        co, ci = a['cuff_o'], a['cuff_i']
        bx, by = lerp(co, ci, .35)
        bx, by = offset_toward((bx, by), a['shoulder'], 30)
        pen.button(2 * CX - bx if flip else bx, by, 6)
    if pocket:
        pts = [(CX + 48, NY + 125), (CX + 130, NY + 125), (CX + 130, NY + 210), (CX + 89, NY + 228), (CX + 48, NY + 210)]
        pen.fill(pts)
        pen.dashed([(CX + 54, NY + 140), (CX + 124, NY + 140)], color=stitch, w=1.4)
    if denim:
        pen.dashed([(CX - 22, NY + 34), (CX - 22, a['hem'] - 6)], color=stitch, w=1.4)
        pen.dashed(bez((CX - a['bw'] - 20, NY + 110), (CX - 60, NY + 150), (CX - 22, NY + 140), n=10), color=stitch, w=1.4)
        pen.dashed(bez((CX + a['bw'] + 20, NY + 110), (CX + 60, NY + 150), (CX + 22, NY + 140), n=10), color=stitch, w=1.4)
    hem_stitch(pen, a, offset=16)
    collar(pen, 56)
    return a


def tank(pen, men=False, ribbed=False, sport_bra=False):
    if sport_bra:
        left, a = top_left(sleeve='none', nw=68, bw=140, strap=42, armhole_y=NY + 185, hem=NY + 330, hem_w=134, curve=2)
        depth = 108
    elif men:
        left, a = top_left(sleeve='none', nw=62, bw=170, strap=52, armhole_y=NY + 245, hem=905)
        depth = 72
    else:
        left, a = top_left(sleeve='none', nw=74, bw=150, strap=36, armhole_y=NY + 195, hem=870, waist_in=10)
        depth = 88
    front = crew(a['nw'], depth)
    outline = full_outline(left, front)
    pen.fill(outline)
    back_neck(pen, front, a['nw'], dip=18)
    if ribbed:
        pen.texture(outline, spacing=11, angle=90, color=pen.band, w=1.6)
        pen.stroke(outline, closed=True)
    neck_band(pen, a['nw'], depth, width=10)
    for flip in (False, True):
        pts = bez(a['shoulder'], (a['shoulder'][0] - 4, NY + 110), (a['armpit'][0] + 34, a['armpit'][1] - 6), a['armpit'], n=14)
        if flip:
            pts = [(2 * CX - x, y) for x, y in pts]
        pen.stroke([(x + (8 if not flip else -8), y) for x, y in pts], w=1.5)
    if sport_bra:
        hw = a['hem_w']
        band = [(CX - hw - 2, a['hem'] - 52), (CX + hw + 2, a['hem'] - 52), (CX + hw, a['hem'] - 2), (CX, a['hem']), (CX - hw, a['hem'] - 2)]
        pen.fill(band, color=pen.band)
        pen.apple(CX, a['hem'] - 26, 14, color=pen.accent)
    else:
        hem_stitch(pen, a, offset=18)
    return a


def puff_top(pen):
    left, a = top_left(sleeve='puff', nw=80, sw=176, bw=142, hem=690, waist_in=8, curve=4)
    front = [(CX + 80, NY), (CX + 80, NY + 66), (CX - 80, NY + 66), (CX - 80, NY)]
    outline = full_outline(left, front)
    pen.fill(outline)
    back_neck(pen, front, 80, dip=8)
    pen.texture(outline, spacing=20, angle=0, color=pen.band, w=1.8,
                box=(CX - a['bw'] + 4, NY + 120, CX + a['bw'] - 4, a['hem'] - 12))
    pen.stroke(outline, closed=True)
    pen.stroke([(CX + 80, NY + 66), (CX - 80, NY + 66)], w=5, color=pen.band)
    for flip in (False, True):
        s, co = a['shoulder'], a['cuff_o']
        for k in range(3):
            pts = bez((s[0] - 10 - k * 14, s[1] + 18 + k * 6), (s[0] - 60 - k * 10, s[1] + 80), (co[0] + 20 - k * 8, co[1] - 20), n=10)
            pen.stroke(pts if not flip else [(2 * CX - x, y) for x, y in pts], w=1.4)
        band = [a['cuff_o'], a['cuff_i'], offset_toward(a['cuff_i'], a['armpit'], 14), offset_toward(a['cuff_o'], s, 14)]
        pen.fill(band if not flip else [(2 * CX - x, y) for x, y in band], color=pen.band)
    return a


def wrap_top(pen):
    left, a = top_left(sleeve='long', nw=72, sw=188, bw=146, hem=730, waist_in=14, sleeve_len=540, curve=4)
    front = [(CX + 72, NY), (CX, NY + 250), (CX - 72, NY)]
    pen.fill(full_outline(left, front))
    back_neck(pen, front, 72, dip=8)
    armhole_seams(pen, a)
    pen.stroke(bez((CX, NY + 250), (CX - 50, NY + 340), (CX - 120, a['hem'] - 60), n=12), w=2.4)
    kx, ky = CX - 128, a['hem'] - 56
    pen.fill([(kx, ky), (kx - 46, ky - 26), (kx - 42, ky + 22)])
    pen.fill([(kx, ky), (kx + 30, ky - 30), (kx + 36, ky + 16)])
    pen.fill([(kx - 6, ky), (kx - 30, ky + 150), (kx - 12, ky + 154), (kx + 6, ky + 6)])
    pen.fill([(kx + 2, ky), (kx + 16, ky + 120), (kx + 32, ky + 116), (kx + 10, ky - 2)])
    pen.dot(kx, ky, 9, color=pen.c, outline=pen.line)
    sleeve_bands(pen, a, depth=20)
    return a


def hoodie(pen, zipped=False, crop=False):
    hem = 730 if crop else 905
    left, a = top_left(sleeve='long', nw=72, sw=206, bw=172, hem=hem, drop=40, curve=4)
    hood(pen)
    front = crew(72, 62)
    pen.fill(full_outline(left, front))
    armhole_seams(pen, a)
    sleeve_bands(pen, a, depth=46, rib=True)
    hem_band(pen, a, height=54)
    pen.stroke(front, w=2.4)
    if zipped:
        pen.stroke([(CX, NY + 62), (CX, a['hem'])], w=5, color=pen.metal)
        pen.dashed([(CX, NY + 64), (CX, a['hem'] - 2)], w=3, dash=3, gap=3, color=pen.line)
        pen.fill([(CX - 7, NY + 70), (CX + 7, NY + 70), (CX + 5, NY + 112), (CX - 5, NY + 112)], color=pen.metal)
        for side in (-1, 1):
            pen.stroke([(CX + side * 70, a['hem'] - 230), (CX + side * 118, a['hem'] - 90)], w=5, color=pen.inner)
    else:
        top_y, bot_y = a['hem'] - 250, a['hem'] - 62
        pocket = [(CX - 112, top_y), (CX + 112, top_y), (CX + 150, bot_y), (CX - 150, bot_y)]
        pen.fill(pocket)
        pen.dashed([(CX - 106, top_y + 10), (CX + 106, top_y + 10)], w=1.4, color=pen.line)
        for side in (-1, 1):
            pen.stroke([(CX + side * 112, top_y), (CX + side * 150, bot_y)], w=3.4)
    for side in (-1, 1):
        x = CX + side * 28
        pen.dot(x, NY + 52, 5, color=pen.inner, outline=pen.line)
        cord = bez((x, NY + 52), (x + side * 4, NY + 120), (x + side * 10, NY + 200), n=10)
        pen.stroke(cord, w=4, color=lighter(pen.c, .6) if lum(pen.c) < .5 else darker(pen.c, .15))
        ex, ey = cord[-1]
        pen.fill([(ex - 4, ey), (ex + 4, ey), (ex + 4, ey + 22), (ex - 4, ey + 22)], color=pen.metal, outline=False)
    if not zipped:
        pen.apple(CX, NY + 150, 16, color=pen.accent)
    return a


def blazer(pen, double=False):
    left, a = top_left(sleeve='long', nw=62, sw=214, bw=172, drop=28, hem=915, hem_w=178,
                       waist_in=12, sleeve_len=575, curve=4)
    vy = NY + (300 if double else 330)
    front = [(CX + 62, NY), (CX, vy), (CX - 62, NY)]
    pen.fill(full_outline(left, front))
    back_neck(pen, front, 62, dip=10, color=darker(pen.c, .32) if lum(pen.c) > .25 else lighter(pen.c, .18))
    stand = arc(CX, NY, 66, 24, 180, 360)
    pen.fill(stand + list(reversed(arc(CX, NY, 62, 8, 180, 360))))
    armhole_seams(pen, a)
    lap = [(CX - 62, NY - 2), (CX - 104, NY + 36), (CX - 94, NY + 64), (CX - 144, NY + 108), (CX - 4, vy)]
    for pts in (lap, [(2 * CX - x, y) for x, y in lap]):
        pen.fill(pts)
        pen.stroke([pts[3], pts[4]], w=3.2, color=pen.inner)
    pen.stroke([(CX, vy), (CX, a['hem'])], w=2.4)
    if double:
        for y in (vy + 50, vy + 140):
            pen.button(CX - 46, y, 10)
            pen.button(CX + 46, y, 10)
    else:
        pen.button(CX + 10, vy + 40, 11)
    for side in (-1, 1):
        x0, x1 = (CX + side * 168, CX + side * 64)
        y0 = a['hem'] - 200
        pen.fill([(min(x0, x1), y0), (max(x0, x1), y0), (max(x0, x1), y0 + 30), (min(x0, x1), y0 + 30)])
    pen.stroke([(CX + 76, NY + 196), (CX + 146, NY + 188)], w=4, color=pen.inner)
    for flip in (False, True):
        co, s = a['cuff_o'], a['shoulder']
        for k in range(3):
            x, y = offset_toward(co, s, 30 + k * 20)
            x += 14
            pen.button(2 * CX - x if flip else x, y, 5)
    return a


def denim_jacket(pen):
    left, a = top_left(sleeve='long', nw=56, sw=214, bw=180, drop=36, hem=800, hem_w=180,
                       sleeve_len=545, curve=2)
    front = crew(56, 34)
    outline = full_outline(left, front)
    pen.fill(outline)
    pen.texture(outline, spacing=7, angle=-60, color=darker(pen.c, .08), w=1)
    pen.stroke(outline, closed=True)
    back_neck(pen, front, 56)
    armhole_seams(pen, a)
    gold = pen.accent
    pen.dashed(bez((CX - a['bw'] - 30, NY + 108), (CX - 80, NY + 132), (CX - 20, NY + 128), n=10), color=gold, w=1.5)
    pen.dashed(bez((CX + a['bw'] + 30, NY + 108), (CX + 80, NY + 132), (CX + 20, NY + 128), n=10), color=gold, w=1.5)
    for side in (-1, 1):
        x0, x1 = CX + side * 60, CX + side * 150
        lo, hi = min(x0, x1), max(x0, x1)
        mid = (lo + hi) / 2
        pen.fill([(lo, NY + 185), (hi, NY + 185), (hi, NY + 262), (lo, NY + 262)])
        flap = [(lo, NY + 150), (hi, NY + 150), (hi, NY + 184), (mid, NY + 206), (lo, NY + 184)]
        pen.fill(flap)
        pen.dashed([(lo + 6, NY + 158), (hi - 6, NY + 158)], color=gold, w=1.4)
        pen.button(mid, NY + 190, 7, color=(176, 141, 87))
        for dx in (-5, 5):
            pen.dashed([(mid + dx, NY + 262), (mid + dx + side * 8, a['hem'] - 56)], color=gold, w=1.4)
    for x in (CX - 18, CX + 18):
        pen.stroke([(x, NY + 32), (x, a['hem'])], w=1.6)
    pen.dashed([(CX - 24, NY + 34), (CX - 24, a['hem'] - 4)], color=gold, w=1.4)
    for y in range(NY + 80, a['hem'] - 60, 94):
        pen.button(CX, y, 8, color=(176, 141, 87))
    band = [(CX - 180, a['hem'] - 56), (CX + 180, a['hem'] - 56), (CX + 180, a['hem'] - 2), (CX, a['hem']), (CX - 180, a['hem'] - 2)]
    pen.fill(band)
    pen.dashed([(CX - 174, a['hem'] - 46), (CX + 174, a['hem'] - 46)], color=gold, w=1.4)
    pen.button(CX - 150, a['hem'] - 28, 7, color=(176, 141, 87))
    pen.button(CX + 150, a['hem'] - 28, 7, color=(176, 141, 87))
    sleeve_bands(pen, a, depth=52)
    collar(pen, 56, spread=40, length=104)
    pen.highlights += [(CX - 110, NY + 360, 50, 120, .22), (CX + 110, NY + 360, 50, 120, .22)]
    return a


def bomber(pen):
    left, a = top_left(sleeve='long', nw=66, sw=216, bw=184, drop=42, hem=820, hem_w=176,
                       sleeve_len=560, curve=2)
    front = crew(66, 44)
    pen.fill(full_outline(left, front))
    back_neck(pen, front, 66)
    armhole_seams(pen, a)
    sleeve_bands(pen, a, depth=50, rib=True)
    hem_band(pen, a, height=62)
    neck_band(pen, 66, 44, width=22)
    for y in (a['hem'] - 44, a['hem'] - 30):
        pen.stroke([(CX - 176, y), (CX + 176, y)], w=3, color=pen.accent)
    pen.stroke([(CX, NY + 44), (CX, a['hem'])], w=5, color=pen.metal)
    pen.dashed([(CX, NY + 46), (CX, a['hem'] - 2)], w=3, dash=3, gap=3, color=pen.line)
    pen.fill([(CX - 7, NY + 50), (CX + 7, NY + 50), (CX + 5, NY + 92), (CX - 5, NY + 92)], color=pen.metal)
    for side in (-1, 1):
        pen.stroke([(CX + side * 160, a['hem'] - 250), (CX + side * 128, a['hem'] - 120)], w=7, color=pen.inner)
    sx, sy = offset_toward(a['shoulder'], a['cuff_o'], 150)
    pen.fill([(2 * CX - sx - 12, sy), (2 * CX - sx + 24, sy + 6), (2 * CX - sx + 20, sy + 50), (2 * CX - sx - 16, sy + 44)])
    return a


def track_jacket(pen, hooded=False, men=False):
    sw, bw = (216, 182) if men else (204, 164)
    left, a = top_left(sleeve='long', nw=58, sw=sw, bw=bw, drop=34, hem=870, sleeve_len=560, curve=3)
    if hooded:
        hood(pen, width=140, inner=False)
    front = crew(58, 24)
    pen.fill(full_outline(left, front))
    armhole_seams(pen, a)
    for flip in (False, True):
        s, co = a['shoulder'], a['cuff_o']
        top_i = offset_toward(a['cuff_o'], s, 46)
        for off in (10, 22):
            pts = [(s[0] + off * .9, s[1] + 8), (top_i[0] + off, top_i[1])]
            if flip:
                pts = [(2 * CX - x, y) for x, y in pts]
            pen.stroke(pts, w=5.5, color=pen.accent)
    sleeve_bands(pen, a, depth=46, rib=True)
    hem_band(pen, a, height=48)
    col = [(CX - 60, NY + 2), (CX - 54, NY - 40), (CX + 54, NY - 40), (CX + 60, NY + 2)] + arc(CX, NY, 60, 24, 0, 180)[1:-1]
    pen.fill(col, color=pen.band)
    pen.stroke([(CX, NY - 40), (CX, a['hem'])], w=5, color=pen.metal)
    pen.dashed([(CX, NY - 38), (CX, a['hem'] - 2)], w=3, dash=3, gap=3, color=pen.line)
    pen.fill([(CX - 7, NY - 32), (CX + 7, NY - 32), (CX + 5, NY + 12), (CX - 5, NY + 12)], color=pen.metal)
    for side in (-1, 1):
        pen.stroke([(CX + side * 150, a['hem'] - 250), (CX + side * 122, a['hem'] - 120)], w=4, color=pen.metal)
    pen.apple(CX + 80, NY + 110, 15, color=pen.accent)
    return a


# --- garments: bottoms -------------------------------------------------------

def pants(pen, style='jeans'):
    ww = 150
    band_h = {'leggings': 72, 'sport_leggings': 80, 'flare': 72}.get(style, 46)
    if style == 'jeans':
        outer = bez((CX - ww, WY), (CX - 180, WY + 130), (CX - 180, WY + 420), (CX - 172, 1040), n=26)
        inner = bez((CX - 30, 1040), (CX - 34, 700), (CX - 18, WY + 300), (CX, WY + 268), n=20)
    elif style == 'wide_jeans':
        outer = bez((CX - ww, WY), (CX - 186, WY + 200), (CX - 214, 700), (CX - 224, 1050), n=26)
        inner = bez((CX - 12, 1050), (CX - 12, 700), (CX - 10, WY + 320), (CX, WY + 268), n=20)
    elif style in ('leggings', 'sport_leggings'):
        ww = 144
        outer = bez((CX - ww, WY), (CX - 176, WY + 220), (CX - 150, WY + 450), (CX - 100, 1062), n=26)
        inner = bez((CX - 42, 1062), (CX - 48, 800), (CX - 8, WY + 330), (CX, WY + 258), n=20)
    elif style == 'flare':
        ww = 144
        outer = bez((CX - ww, WY), (CX - 180, WY + 300), (CX - 92, 740), (CX - 168, 1062), n=26)
        inner = bez((CX - 20, 1062), (CX - 58, 800), (CX - 6, WY + 330), (CX, WY + 258), n=20)
    elif style == 'joggers':
        outer = bez((CX - ww, WY), (CX - 188, WY + 200), (CX - 176, 720), (CX - 150, 962), n=26) + [(CX - 138, 1036)]
        inner = [(CX - 64, 1036)] + bez((CX - 58, 962), (CX - 44, 700), (CX - 12, WY + 320), (CX, WY + 278), n=20)
    elif style == 'wide_sweats':
        outer = bez((CX - ww, WY), (CX - 192, WY + 220), (CX - 206, 700), (CX - 210, 1046), n=26)
        inner = bez((CX - 18, 1046), (CX - 18, 700), (CX - 12, WY + 330), (CX, WY + 278), n=20)
    else:  # shorts
        outer = bez((CX - ww, WY), (CX - 180, WY + 120), (CX - 194, WY + 260), (CX - 200, WY + 372), n=16)
        inner = bez((CX - 24, WY + 404), (CX - 16, WY + 330), (CX - 6, WY + 290), (CX, WY + 266), n=12)
    left = [(CX, WY)] + outer + inner
    outline = full_outline(left)
    pen.fill(outline)

    denim = 'jeans' in style
    if denim:
        pen.texture(outline, spacing=7, angle=-60, color=darker(pen.c, .08), w=1)
        pen.stroke(outline, closed=True)
        pen.highlights += [(CX - 96, WY + 330, 44, 150, .26), (CX + 96, WY + 330, 44, 150, .26),
                           (CX - 104, 780, 40, 70, .18), (CX + 104, 780, 40, 70, .18)]
    band = [(CX - ww, WY), (CX + ww, WY), (CX + ww + 2, WY + band_h), (CX - ww - 2, WY + band_h)]
    pen.fill(band, color=pen.c if denim else pen.band)

    if denim:
        gold = pen.accent
        pen.dashed([(CX - ww + 4, WY + band_h - 8), (CX + ww - 4, WY + band_h - 8)], color=gold, w=1.4)
        pen.button(CX + 2, WY + 22, 9, color=(176, 141, 87))
        for x in (CX - 70, CX + 70, CX - 136, CX + 136):
            pen.fill([(x - 7, WY - 4), (x + 7, WY - 4), (x + 7, WY + band_h + 8), (x - 7, WY + band_h + 8)])
        pen.stroke([(CX, WY + band_h), (CX, WY + 222)], w=2)
        pen.dashed([(CX + 38, WY + band_h + 2)] + bez((CX + 38, WY + 160), (CX + 38, WY + 205), (CX + 2, WY + 222), n=8), color=gold, w=1.5)
        for side in (-1, 1):
            pts = bez((CX + side * 98, WY + band_h), (CX + side * 104, WY + 112), (CX + side * (ww + 20), WY + 122), n=12)
            pen.stroke(pts, w=2.4)
            pen.dashed([(x + side * -6, y + 6) for x, y in pts], color=gold, w=1.3)
            pen.dot(CX + side * (ww + 1), WY + band_h + 8, 3.5, color=(176, 141, 87))
        pen.dashed(bez((CX - 100, WY + band_h + 2), (CX - 96, WY + 90), (CX - 70, WY + 96), n=6), color=gold, w=1.2)
        for side in (-1, 1):
            hem_y = 1040 if style == 'jeans' else 1050
            x_out = 172 if style == 'jeans' else 224
            x_in = 30 if style == 'jeans' else 12
            pen.dashed([(CX + side * (x_out - 2), hem_y - 22), (CX + side * (x_in + 2), hem_y - 22)], color=gold, w=1.4)
    elif style in ('leggings', 'sport_leggings', 'flare'):
        pen.stroke([(CX, WY + band_h), (CX, WY + 256)], w=1.8)
        pen.stroke([(CX - ww - 1, WY + band_h - 12), (CX + ww + 1, WY + band_h - 12)], w=1.4)
        if style == 'sport_leggings':
            for side in (-1, 1):
                pts = bez((CX + side * (ww + 10), WY + band_h + 30), (CX + side * 150, WY + 380), (CX + side * 128, WY + 600), (CX + side * 84, 1040), n=20)
                pen.stroke(pts, w=3, color=pen.accent)
                pen.stroke([(x - side * 16, y) for x, y in pts], w=1.4, color=pen.line)
            pen.apple(CX - 90, WY + 40, 14, color=pen.accent)
        pen.highlights += [(CX - 110, WY + 380, 22, 220, .16), (CX + 110, WY + 380, 22, 220, .16)]
    else:
        pen.texture(band, spacing=12, angle=90, color=pen.line, w=1.2)
        pen.stroke(band, closed=True)
        for side in (-1, 1):
            x = CX + side * 18
            pen.dot(x, WY + 30, 4.5, color=pen.inner, outline=pen.line)
            cord = bez((x, WY + 30), (x + side * 10, WY + 110), (x + side * 22, WY + 170), n=10)
            pen.stroke(cord, w=4, color=lighter(pen.c, .6) if lum(pen.c) < .5 else darker(pen.c, .15))
            ex, ey = cord[-1]
            pen.fill([(ex - 4, ey), (ex + 4, ey), (ex + 4, ey + 20), (ex - 4, ey + 20)], color=pen.metal, outline=False)
            pen.stroke([(CX + side * 118, WY + band_h + 2), (CX + side * 170, WY + 175)], w=2.4)
        if style == 'joggers':
            for side in (-1, 1):
                cuff = [(CX + side * 150, 962), (CX + side * 138, 1036), (CX + side * 64, 1036), (CX + side * 58, 962)]
                pen.fill(cuff, color=pen.band)
                pen.texture(cuff, spacing=9, angle=90, color=pen.line, w=1)
                pen.stroke(cuff, closed=True, w=2)
                for k in range(3):
                    y = 890 - k * 26
                    pen.stroke(bez((CX + side * 140, y), (CX + side * 110, y + 12), (CX + side * 76, y + 2), n=8), w=1.2)
        elif style == 'shorts':
            for side in (-1, 1):
                pts = bez((CX + side * (ww + 4), WY + band_h), (CX + side * 176, WY + 150), (CX + side * 190, WY + 260), (CX + side * 196, WY + 368), n=12)
                pen.stroke([(x - side * 12, y) for x, y in pts], w=5, color=pen.accent)
                pen.stroke([(CX + side * 196, WY + 350), (CX + side * 26, WY + 384)], w=1.4)
            pen.apple(CX - 110, WY + 330, 14, color=pen.accent)
        else:
            for side in (-1, 1):
                pen.stroke([(CX + side * 208, 1022), (CX + side * 20, 1022)], w=1.6)
    return {'hem': 1060}


# --- garments: dresses -------------------------------------------------------

def slip_dress(pen):
    for side in (-1, 1):
        pen.stroke([(CX + side * 70, NY - 6), (CX + side * 92, NY + 94)], w=5, color=darker(pen.c, .15) if lum(pen.c) > .25 else lighter(pen.c, .2))
    left = [(CX - 60, NY + 84), (CX - 124, NY + 104), (CX - 116, NY + 310), (CX - 150, NY + 450)] + \
        bez((CX - 150, NY + 450), (CX - 200, 800), (CX - 238, 1086), n=16)[1:] + \
        bez((CX - 238, 1086), (CX - 120, 1102), (CX, 1102), n=10)[1:]
    front = bez((CX + 60, NY + 84), (CX + 30, NY + 156), (CX - 30, NY + 156), (CX - 60, NY + 84), n=16)
    pen.fill(full_outline(left, front))
    pen.fill([(CX - 60, NY + 84), (CX + 60, NY + 84)] + front[1:-1], color=pen.inner)
    for k in range(2):
        pen.stroke(bez((CX - 50 + k * 10, NY + 118 + k * 22), (CX, NY + 170 + k * 28), (CX + 50 - k * 10, NY + 118 + k * 22), n=12), w=1.5)
    for x0, x1 in ((CX - 70, CX - 150), (CX - 20, CX - 60), (CX + 30, CX + 50), (CX + 80, CX + 160)):
        pen.stroke(bez((x0, NY + 330), (x0 - (x0 - CX) * .05, 760), (x1, 1080), n=16), w=1.4)
    pen.highlights += [(CX - 58, 700, 16, 280, .32), (CX + 92, 760, 12, 230, .26), (CX - 10, NY + 230, 50, 40, .18)]
    return {'hem': 1100}


def tiered_dress(pen):
    left = [(CX - 70, NY), (CX - 106, NY)] + bez((CX - 106, NY), (CX - 108, NY + 90), (CX - 124, NY + 160), (CX - 134, NY + 172), n=12)[1:] + \
        [(CX - 120, NY + 300), (CX - 158, NY + 470), (CX - 180, NY + 470), (CX - 214, NY + 645), (CX - 236, NY + 645), (CX - 266, 1088)] + \
        bez((CX - 266, 1088), (CX - 130, 1102), (CX, 1102), n=10)[1:]
    front = [(CX + 70, NY), (CX + 70, NY + 62), (CX - 70, NY + 62), (CX - 70, NY)]
    outline = full_outline(left, front)
    pen.fill(outline)
    back_neck(pen, front, 70, dip=10)
    pen.texture(outline, spacing=18, angle=0, color=pen.band, w=1.6, box=(CX - 126, NY + 120, CX + 126, NY + 296))
    for y, hw in ((NY + 300, 120), (NY + 470, 180), (NY + 645, 236)):
        pen.stroke([(CX - hw, y), (CX + hw, y)], w=2.2)
        for x in range(CX - hw + 10, CX + hw - 6, 16):
            pen.stroke([(x, y + 4), (x + (x - CX) * .03, y + 26)], w=1.1)
    pen.stroke(front, w=4, color=pen.band)
    return {'hem': 1100}


# --- registry ----------------------------------------------------------------

GARMENTS = {
    'tee': (tee, 'top'),
    'tee_oversized': (lambda p: tee(p, oversized=True), 'top'),
    'tee_dress': (lambda p: tee(p, dress=True), 'top'),
    'sport_tee': (lambda p: tee(p, sport=True), 'top'),
    'men_sport_tee': (lambda p: tee(p, sport=True, men=True), 'top'),
    'shirt': (shirt, 'top'),
    'shirt_oversized': (lambda p: shirt(p, pocket=True, oversized=True), 'top'),
    'denim_shirt': (lambda p: shirt(p, pocket=True, denim=True), 'top'),
    'tank': (lambda p: tank(p, ribbed=True), 'top'),
    'tank_scoop': (tank, 'top'),
    'men_tank': (lambda p: tank(p, men=True), 'top'),
    'sports_bra': (lambda p: tank(p, sport_bra=True), 'top'),
    'puff_top': (puff_top, 'top'),
    'wrap_top': (wrap_top, 'top'),
    'hoodie': (hoodie, 'top'),
    'zip_hoodie': (lambda p: hoodie(p, zipped=True, crop=True), 'top'),
    'blazer': (blazer, 'top'),
    'blazer_double': (lambda p: blazer(p, double=True), 'top'),
    'denim_jacket': (denim_jacket, 'top'),
    'bomber': (bomber, 'top'),
    'track_jacket': (track_jacket, 'top'),
    'men_track_jacket': (lambda p: track_jacket(p, men=True), 'top'),
    'windbreaker': (lambda p: track_jacket(p, hooded=True, men=True), 'top'),
    'polo': (lambda p: polo(p), 'top'),
    'jeans': (lambda p: pants(p, 'jeans'), 'bottom'),
    'wide_jeans': (lambda p: pants(p, 'wide_jeans'), 'bottom'),
    'leggings': (lambda p: pants(p, 'leggings'), 'bottom'),
    'sport_leggings': (lambda p: pants(p, 'sport_leggings'), 'bottom'),
    'flare_leggings': (lambda p: pants(p, 'flare'), 'bottom'),
    'joggers': (lambda p: pants(p, 'joggers'), 'bottom'),
    'wide_sweats': (lambda p: pants(p, 'wide_sweats'), 'bottom'),
    'shorts': (lambda p: pants(p, 'shorts'), 'bottom'),
    'slip_dress': (slip_dress, 'top'),
    'tiered_dress': (tiered_dress, 'top'),
}


def polo(pen):
    left, a = top_left(sleeve='short', nw=56, sw=202, bw=166, hem=905, curve=14)
    front = crew(56, 30)
    pen.fill(full_outline(left, front))
    back_neck(pen, front, 56)
    armhole_seams(pen, a)
    sleeve_bands(pen, a, depth=24, rib=True)
    placket = [(CX - 18, NY + 24), (CX + 18, NY + 24), (CX + 18, NY + 178), (CX - 18, NY + 178)]
    pen.fill(placket)
    for y in (NY + 72, NY + 134):
        pen.button(CX, y, 6.5)
    hem_stitch(pen, a, offset=18)
    for side in (-1, 1):
        pen.stroke([(CX + side * (a['hem_w'] - 2), a['hem'] - 14), (CX + side * (a['hem_w'] - 6), a['hem'] - 60)], w=2)
    collar(pen, 56, spread=34, length=80, rounded=True)
    pen.apple(CX + 96, NY + 118, 15, color=pen.accent)
    return a


# --- composition -------------------------------------------------------------

def _hanger(bg_draw, kind):
    wire = (126, 116, 106)
    wood, wood_dark = (190, 158, 122), (150, 118, 86)
    if kind == 'top':
        hook_base = NY - 22
        bar = [(CX - 196, NY + 36), (CX, NY - 22), (CX + 196, NY + 36)]
        bg_draw.line(P(bar), fill=wood_dark, width=16 * S, joint='curve')
        bg_draw.line(P(bar), fill=wood, width=11 * S, joint='curve')
    else:
        hook_base = WY - 20
        bg_draw.rounded_rectangle(P([(CX - 222, WY - 30), (CX + 222, WY - 12)]), radius=8 * S, fill=wood, outline=wood_dark, width=2 * S)
    pts = [(CX, hook_base), (CX, hook_base - 44)] + arc(CX + 24, hook_base - 44, 24, 24, 180, 360, n=18)[1:] + [(CX + 48, hook_base - 34)]
    bg_draw.line(P(pts), fill=wire, width=5 * S, joint='curve')


def _clips(img):
    d = ImageDraw.Draw(img)
    for x in (CX - 172, CX + 172):
        d.rounded_rectangle(P([(x - 13, WY - 34), (x + 13, WY + 22)]), radius=4 * S, fill=(118, 110, 102), outline=(90, 84, 78), width=S)


def _light(layer, highlights):
    """Soft top light, bottom shade and optional fabric highlights."""
    alpha = layer.getchannel('A')
    grad = Image.linear_gradient('L').resize(layer.size)
    white_a = grad.point(lambda v: int(max(0, 140 - v) * .26))
    black_a = grad.point(lambda v: int(max(0, v - 120) * .20))
    for color, a in (((255, 255, 255), white_a), ((25, 10, 12), black_a)):
        over = Image.new('RGBA', layer.size, color + (0,))
        over.putalpha(ImageChops.multiply(a, alpha))
        layer.alpha_composite(over)
    if highlights:
        small = (layer.size[0] // 4, layer.size[1] // 4)
        mask = Image.new('L', small, 0)
        md = ImageDraw.Draw(mask)
        for cx, cy, rx, ry, strength in highlights:
            k = S / 4
            md.ellipse([(cx - rx) * k, (cy - ry) * k, (cx + rx) * k, (cy + ry) * k], fill=int(255 * strength))
        mask = mask.filter(ImageFilter.GaussianBlur(10)).resize(layer.size, Image.BILINEAR)
        over = Image.new('RGBA', layer.size, (255, 255, 255, 0))
        over.putalpha(ImageChops.multiply(mask, alpha))
        layer.alpha_composite(over)
    return layer


def _garment(kind, color, accent):
    fn, hanger = GARMENTS[kind]
    pen = Pen(color, accent)
    fn(pen)
    return _light(pen.img, pen.highlights), hanger


def _shadow(layer, strength=.26, blur=9, offset=(10, 22)):
    alpha = layer.getchannel('A')
    small = alpha.resize((alpha.size[0] // 4, alpha.size[1] // 4)).filter(ImageFilter.GaussianBlur(blur))
    shadow_a = small.resize(alpha.size, Image.BILINEAR).point(lambda v: int(v * strength))
    shadow = Image.new('RGBA', layer.size, (60, 28, 30, 0))
    shadow.putalpha(shadow_a)
    out = Image.new('RGBA', layer.size, (0, 0, 0, 0))
    out.alpha_composite(shadow, (offset[0] * S, offset[1] * S))
    return out


def _background(bg):
    img = Image.new('RGBA', (W * S, H * S), bg + (255,))
    grad = Image.radial_gradient('L').resize(img.size)
    vignette = Image.new('RGBA', img.size, darker(bg, .10) + (0,))
    vignette.putalpha(grad.point(lambda v: int(v * .55)))
    img.alpha_composite(vignette)
    return img


def pick_background(color, seed=0):
    options = [(243, 237, 229), (241, 230, 225), (234, 233, 224), (238, 233, 227), (245, 240, 234)]
    if lum(color) > .78:
        options = [(226, 214, 200), (219, 222, 212), (228, 214, 210), (214, 206, 196)]
    return random.Random(seed).choice(options)


def _fit(subject, box_w=.80, box_h=.86, max_scale=1.35):
    """Scale and centre the drawn subject so it fills the frame like a product shot."""
    bbox = subject.getbbox()
    if not bbox:
        return subject
    cropped = subject.crop(bbox)
    k = min(W * S * box_w / cropped.width, H * S * box_h / cropped.height, max_scale)
    cropped = cropped.resize((int(cropped.width * k), int(cropped.height * k)), Image.LANCZOS)
    out = Image.new('RGBA', subject.size, (0, 0, 0, 0))
    out.alpha_composite(cropped, ((out.width - cropped.width) // 2, (out.height - cropped.height) // 2))
    return out


def render(kind, color_hex, bg=None, accent_hex=None, seed=0, bottom=None, bottom_hex=None):
    """Return JPEG bytes of a garment (or a top+bottom set when `bottom` is given)."""
    color = rgb(color_hex)
    accent = rgb(accent_hex) if accent_hex else None
    bg = bg or pick_background(color, seed)
    canvas = _background(bg)

    subject = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    if bottom:
        top_layer, _ = _garment(kind, color, accent)
        bottom_layer, _ = _garment(bottom, rgb(bottom_hex) if bottom_hex else color, accent)
        top_layer = top_layer.crop(top_layer.getbbox()).rotate(-4, expand=True, resample=Image.BICUBIC)
        bottom_layer = bottom_layer.crop(bottom_layer.getbbox()).rotate(3, expand=True, resample=Image.BICUBIC)
        overlap = 60 * S
        tall = Image.new('RGBA', (max(top_layer.width, bottom_layer.width) + 120 * S,
                                  top_layer.height + bottom_layer.height - overlap), (0, 0, 0, 0))
        tall.alpha_composite(bottom_layer, ((tall.width - bottom_layer.width) // 2 + 36 * S, top_layer.height - overlap))
        tall.alpha_composite(top_layer, ((tall.width - top_layer.width) // 2 - 30 * S, 0))
        k = min(subject.width * .78 / tall.width, subject.height * .9 / tall.height)
        tall = tall.resize((int(tall.width * k), int(tall.height * k)), Image.LANCZOS)
        subject.alpha_composite(tall, ((subject.width - tall.width) // 2, (subject.height - tall.height) // 2))
        canvas.alpha_composite(_shadow(subject, strength=.22, offset=(6, 12)))
        canvas.alpha_composite(subject)
    else:
        layer, hanger = _garment(kind, color, accent)
        _hanger(ImageDraw.Draw(subject), hanger)
        subject.alpha_composite(layer)
        if hanger == 'bottom':
            _clips(subject)
        subject = _fit(subject)
        canvas.alpha_composite(_shadow(subject))
        canvas.alpha_composite(subject)

    out = canvas.convert('RGB').resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, 'JPEG', quality=86, optimize=True, progressive=True)
    return buf.getvalue()
