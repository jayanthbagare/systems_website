"""Convert the PPTX into HTML slide fragments on a 1920x1080 canvas.

Every color is emitted as a CSS custom property with the original value as
fallback (--f-HEX for fills, --t-HEX for text, --l-HEX for lines), so themes
can remap any color without touching slide files.
"""
import os, re, json, math, html, sys
from pptx import Presentation
from PIL import Image
from io import BytesIO

import argparse
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('pptx', help='PowerPoint file to convert')
ap.add_argument('out', help='site folder (the one containing index.html)')
ap.add_argument('--prefix', default='',
                help='convert a NEW deck without touching existing slides: file and image names get this '
                     'prefix, slides/manifest.js is left alone, and the lines to paste into it are printed')
args = ap.parse_args()
SRC, OUT, PREFIX = args.pptx, args.out, args.prefix
EMU_PX = 1920 / 12192000  # 1 px = 6350 EMU
NS = {
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}
A = '{%s}' % NS['a']
P = '{%s}' % NS['p']
R = '{%s}' % NS['r']

prs = Presentation(SRC)
theme_colors = {'dk1': '000000', 'lt1': 'FFFFFF', 'dk2': '44546A', 'lt2': 'E7E6E6',
                'tx1': '000000', 'bg1': 'FFFFFF', 'tx2': '44546A', 'bg2': 'E7E6E6',
                'accent1': '4472C4', 'accent2': 'ED7D31', 'accent3': 'A5A5A5',
                'accent4': 'FFC000', 'accent5': '5B9BD5', 'accent6': '70AD47',
                'hlink': '0563C1', 'folHlink': '954F72'}

FONT_STACKS = {
    'georgia': "Georgia, Gelasio, 'Times New Roman', serif",
    'calibri': "Calibri, Carlito, 'Segoe UI', system-ui, sans-serif",
    'trebuchet ms': "'Trebuchet MS', Carlito, 'Segoe UI', sans-serif",
    'consolas': "Consolas, 'SFMono-Regular', Menlo, 'Courier New', monospace",
    'arial': "Arial, Helvetica, sans-serif",
}

def font_stack(name):
    if not name:
        name = 'Arial'
    return FONT_STACKS.get(name.lower(), f"'{name}', Arial, sans-serif")

def px(v):
    return round(int(v) * EMU_PX, 2)

def fmt(n):
    s = ('%.2f' % n).rstrip('0').rstrip('.')
    return s if s not in ('-0', '') else '0'

# ---------------------------------------------------------------- colors
def color_of(parent):
    """parent contains srgbClr/schemeClr/prstClr. Returns (hex, alpha) or None."""
    if parent is None:
        return None
    for c in parent:
        tag = c.tag.replace(A, '')
        if tag == 'srgbClr':
            hexv = c.get('val').upper()
        elif tag == 'schemeClr':
            hexv = theme_colors.get(c.get('val'), '000000')
        elif tag == 'prstClr':
            hexv = {'black': '000000', 'white': 'FFFFFF'}.get(c.get('val'), '000000')
        elif tag == 'sysClr':
            hexv = (c.get('lastClr') or '000000').upper()
        else:
            continue
        alpha = 1.0
        rr, gg, bb = int(hexv[0:2], 16), int(hexv[2:4], 16), int(hexv[4:6], 16)
        lm, lo = None, None
        for m in c:
            mt = m.tag.replace(A, '')
            if mt == 'alpha':
                alpha = int(m.get('val')) / 100000
            elif mt == 'lumMod':
                lm = int(m.get('val')) / 100000
            elif mt == 'lumOff':
                lo = int(m.get('val')) / 100000
        if lm is not None or lo is not None:
            import colorsys
            h, l, s = colorsys.rgb_to_hls(rr / 255, gg / 255, bb / 255)
            l = min(1, max(0, l * (lm or 1) + (lo or 0)))
            r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
            hexv = '%02X%02X%02X' % (round(r2 * 255), round(g2 * 255), round(b2 * 255))
        return hexv, alpha
    return None

def css_color(c, kind):
    hexv, alpha = c
    base = f'var(--{kind}-{hexv},#{hexv})'
    if alpha >= 0.999:
        return base
    return f'color-mix(in srgb,{base} {fmt(alpha * 100)}%,transparent)'

def luminance(hexv):
    r, g, b = (int(hexv[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

# ---------------------------------------------------------------- media
os.makedirs(os.path.join(OUT, 'media'), exist_ok=True)
media_done = {}
alpha_urls = set()

def export_image(part, disp_w, disp_h):
    """Export an image part to webp sized for display. Returns relative url."""
    key = part.partname
    target_w = min(2560, max(64, int(disp_w * 1.5)))
    if key in media_done and media_done[key][1] >= target_w:
        return media_done[key][0]
    base = os.path.splitext(os.path.basename(str(key)))[0]
    im = Image.open(BytesIO(part.blob))
    im.load()
    if im.mode in ('P', 'LA', 'L'):
        im = im.convert('RGBA')
    elif im.mode == 'CMYK':
        im = im.convert('RGB')
    w, h = im.size
    tw = min(w, target_w)
    if tw < w:
        im = im.resize((tw, round(h * tw / w)), Image.LANCZOS)
    has_alpha = im.mode == 'RGBA' and im.getextrema()[3][0] < 255
    if not has_alpha and im.mode != 'RGB':
        im = im.convert('RGB')
    name = f'{PREFIX}{base}.webp'
    im.save(os.path.join(OUT, 'media', name), 'WEBP', quality=84, method=5)
    url = f'media/{name}'
    media_done[key] = (url, tw)
    dark = False
    if has_alpha:
        small = im.convert('RGBA').resize((64, 64))
        px_ = [p for p in small.getdata() if p[3] > 128]
        if px_:
            lum = sum(0.2126*p[0] + 0.7152*p[1] + 0.0722*p[2] for p in px_) / len(px_) / 255
            chroma = sum(max(p[:3]) - min(p[:3]) for p in px_) / len(px_) / 255
            dark = lum < 0.45 and chroma < 0.18
    alpha_urls.add(url) if dark else alpha_urls.discard(url)
    return url

# ---------------------------------------------------------------- geometry
class Xf:
    """Maps shape-local EMU coords to slide EMU (handles group transforms)."""
    def __init__(self, ox=0, oy=0, sx=1, sy=1):
        self.ox, self.oy, self.sx, self.sy = ox, oy, sx, sy
    def box(self, x, y, w, h):
        return self.ox + x * self.sx, self.oy + y * self.sy, w * self.sx, h * self.sy
    def child(self, grpSpPr):
        xfrm = grpSpPr.find(A + 'xfrm')
        off, ext = xfrm.find(A + 'off'), xfrm.find(A + 'ext')
        choff, chext = xfrm.find(A + 'chOff'), xfrm.find(A + 'chExt')
        x, y, w, h = self.box(int(off.get('x')), int(off.get('y')), int(ext.get('cx')), int(ext.get('cy')))
        cw = int(chext.get('cx')) or 1
        ch = int(chext.get('cy')) or 1
        sx, sy = w / cw, h / ch
        return Xf(x - int(choff.get('x')) * sx, y - int(choff.get('y')) * sy, sx, sy)

def get_xfrm(spPr):
    xfrm = spPr.find(A + 'xfrm') if spPr is not None else None
    if xfrm is None:
        return None
    off, ext = xfrm.find(A + 'off'), xfrm.find(A + 'ext')
    if off is None or ext is None:
        return None
    return dict(x=int(off.get('x')), y=int(off.get('y')), w=int(ext.get('cx')), h=int(ext.get('cy')),
                rot=int(xfrm.get('rot', 0)) / 60000, flipH=xfrm.get('flipH') == '1', flipV=xfrm.get('flipV') == '1')

def box_style(xf, g):
    x, y, w, h = xf.box(g['x'], g['y'], g['w'], g['h'])
    s = f'left:{fmt(px(x))}px;top:{fmt(px(y))}px;width:{fmt(px(w))}px;height:{fmt(px(h))}px'
    if g['rot']:
        s += f';transform:rotate({fmt(g["rot"])}deg)'
    return s, (px(x), px(y), px(w), px(h))

def fill_css(spPr):
    if spPr is None:
        return None
    sf = spPr.find(A + 'solidFill')
    if sf is not None:
        c = color_of(sf)
        return css_color(c, 'f') if c else None
    return None

def line_info(spPr):
    ln = spPr.find(A + 'ln') if spPr is not None else None
    if ln is None or ln.find(A + 'noFill') is not None:
        return None
    sf = ln.find(A + 'solidFill')
    if sf is None:
        return None
    c = color_of(sf)
    w = max(0.75, int(ln.get('w', 12700)) * EMU_PX)
    dash = ln.find(A + 'prstDash')
    dashed = dash is not None and dash.get('val') not in (None, 'solid')
    head = ln.find(A + 'headEnd')
    tail = ln.find(A + 'tailEnd')
    return dict(color=css_color(c, 'l'), w=w, dashed=dashed,
                head=(head.get('type') if head is not None else 'none'),
                tail=(tail.get('type') if tail is not None else 'none'))

def shadow_css(spPr):
    sh = spPr.find(f'{A}effectLst/{A}outerShdw') if spPr is not None else None
    if sh is None:
        return None
    dist = int(sh.get('dist', 0)) * EMU_PX
    ang = math.radians(int(sh.get('dir', 0)) / 60000)
    blur = int(sh.get('blurRad', 0)) * EMU_PX
    c = color_of(sh) or ('000000', 0.3)
    return f'box-shadow:{fmt(dist * math.cos(ang))}px {fmt(dist * math.sin(ang))}px {fmt(blur)}px {css_color(c, "f")}'

# ---------------------------------------------------------------- text
def run_style(rPr, default_sz=1400):
    st = []
    sz = default_sz
    font = None
    col = None
    b = i = u = False
    if rPr is not None:
        sz = int(rPr.get('sz', default_sz))
        b = rPr.get('b') == '1'
        i = rPr.get('i') == '1'
        u = rPr.get('u') not in (None, 'none')
        lat = rPr.find(A + 'latin')
        if lat is not None:
            font = lat.get('typeface')
        sf = rPr.find(A + 'solidFill')
        if sf is not None:
            col = color_of(sf)
    st.append(f'font-size:{fmt(sz / 100 * 2)}px')
    st.append(f'font-family:{font_stack(font)}')
    if b: st.append('font-weight:700')
    if i: st.append('font-style:italic')
    if u: st.append('text-decoration:underline')
    st.append('color:' + css_color(col or ('000000', 1), 't'))
    return ';'.join(st), sz

def text_html(txBody, rels):
    bodyPr = txBody.find(A + 'bodyPr')
    out = []
    first_sz = None
    plain = []
    for p in txBody.findall(A + 'p'):
        pPr = p.find(A + 'pPr')
        pst = []
        algn = pPr.get('algn') if pPr is not None else None
        if algn in ('ctr', 'r', 'just'):
            pst.append('text-align:' + {'ctr': 'center', 'r': 'right', 'just': 'justify'}[algn])
        marL = int(pPr.get('marL', 0)) if pPr is not None else 0
        indent = int(pPr.get('indent', 0)) if pPr is not None else 0
        lh = 1.2
        sb = sa = 0
        bullet = None
        if pPr is not None:
            ls = pPr.find(f'{A}lnSpc/{A}spcPct')
            if ls is not None:
                lh = 1.2 * int(ls.get('val')) / 100000
            sbp = pPr.find(f'{A}spcBef/{A}spcPts')
            if sbp is not None:
                sb = int(sbp.get('val')) / 100 * 2
            sap = pPr.find(f'{A}spcAft/{A}spcPts')
            if sap is not None:
                sa = int(sap.get('val')) / 100 * 2
            bu = pPr.find(A + 'buChar')
            if bu is not None and pPr.find(A + 'buNone') is None:
                bullet = bu.get('char')
        pst.append(f'line-height:{fmt(lh)}')
        if sb: pst.append(f'margin-top:{fmt(sb)}px')
        if sa: pst.append(f'margin-bottom:{fmt(sa)}px')
        if marL: pst.append(f'padding-left:{fmt(px(marL))}px')
        if indent and not bullet: pst.append(f'text-indent:{fmt(px(indent))}px')
        runs = []
        ptext = []
        max_sz = 0
        first_rstyle = None
        for el in p:
            t = el.tag.replace(A, '')
            if t == 'r':
                rPr = el.find(A + 'rPr')
                st, sz = run_style(rPr)
                max_sz = max(max_sz, sz)
                if first_rstyle is None: first_rstyle = st
                txt = html.escape(el.findtext(A + 't') or '')
                ptext.append(el.findtext(A + 't') or '')
                link = rPr.find(A + 'hlinkClick') if rPr is not None else None
                if link is not None and link.get(R + 'id') in rels:
                    href = html.escape(rels[link.get(R + 'id')], quote=True)
                    runs.append(f'<a href="{href}" target="_blank" rel="noopener" style="{st}">{txt}</a>')
                else:
                    runs.append(f'<span style="{st}">{txt}</span>')
            elif t == 'br':
                runs.append('<br>')
                ptext.append('\n')
            elif t == 'fld':
                rPr = el.find(A + 'rPr')
                st, sz = run_style(rPr)
                runs.append(f'<span style="{st}">{html.escape(el.findtext(A + "t") or "")}</span>')
        end = p.find(A + 'endParaRPr')
        if not ''.join(ptext).replace('\n', ''):
            st, sz = run_style(end)
            runs.append(f'<span style="{st}">&#8203;</span>')
            max_sz = max(max_sz, sz)
        if bullet:
            hang = -px(indent) if indent < 0 else 24
            bst = first_rstyle or run_style(end)[0]
            runs.insert(0, f'<span class="bu" style="{bst};width:{fmt(hang)}px;margin-left:-{fmt(hang)}px">{html.escape(bullet)}</span>')
        if first_sz is None and ''.join(ptext).strip():
            first_sz = max_sz
        plain.append(''.join(ptext))
        out.append(f'<p style="{";".join(pst)}">{"".join(runs)}</p>')
    # body properties
    bst = []
    ins = {k: int(bodyPr.get(k, d)) for k, d in (('lIns', 91440), ('tIns', 45720), ('rIns', 91440), ('bIns', 45720))}
    bst.append('padding:{}px {}px {}px {}px'.format(*(fmt(px(ins[k])) for k in ('tIns', 'rIns', 'bIns', 'lIns'))))
    anchor = bodyPr.get('anchor', 't')
    bst.append('justify-content:' + {'t': 'flex-start', 'ctr': 'center', 'b': 'flex-end'}.get(anchor, 'flex-start'))
    if bodyPr.get('wrap') == 'none':
        bst.append('white-space:pre')
    text = '\n'.join(plain).strip()
    return f'<div class="tx" style="{";".join(bst)}">{"".join(out)}</div>', text, first_sz or 0

# ---------------------------------------------------------------- shapes
PAGE_NUM = re.compile(r'^\s*\d+\s*/\s*\d+\s*$')

def svg_line(style_box, g, li):
    x, y, w, h = style_box
    x1, y1, x2, y2 = 0, 0, w, h
    if g['flipH']: x1, x2 = x2, x1
    if g['flipV']: y1, y2 = y2, y1
    pad = li['w'] * 4 + 4
    vx, vy = min(x1, x2) - pad, min(y1, y2) - pad
    vw, vh = abs(x2 - x1) + 2 * pad, abs(y2 - y1) + 2 * pad
    mid = []
    defs = ''
    if li['head'] not in (None, 'none') or li['tail'] not in (None, 'none'):
        defs = ('<defs><marker id="{id}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" '
                'orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{c}"/></marker></defs>')
    mid_id = 'm' + str(abs(hash((x, y, w, h))) % 10**8)
    attrs = ''
    if li['tail'] not in (None, 'none'): attrs += f' marker-end="url(#{mid_id})"'
    if li['head'] not in (None, 'none'): attrs += f' marker-start="url(#{mid_id})"'
    dash = f' stroke-dasharray="{fmt(li["w"] * 4)} {fmt(li["w"] * 3)}"' if li['dashed'] else ''
    rot = f';transform:rotate({fmt(g["rot"])}deg)' if g['rot'] else ''
    return (f'<svg class="s ln" style="left:{fmt(x + vx)}px;top:{fmt(y + vy)}px;width:{fmt(vw)}px;height:{fmt(vh)}px{rot}" '
            f'viewBox="{fmt(vx)} {fmt(vy)} {fmt(vw)} {fmt(vh)}">'
            + (defs.format(id=mid_id, c=li['color']) if defs else '') +
            f'<line x1="{fmt(x1)}" y1="{fmt(y1)}" x2="{fmt(x2)}" y2="{fmt(y2)}" stroke="{li["color"]}" '
            f'stroke-width="{fmt(li["w"])}"{dash}{attrs}/></svg>')

def svg_arc(sb, g, spPr, li, fill):
    x, y, w, h = sb
    gd = {e.get('name'): e.get('fmla') for e in spPr.iter(A + 'gd')}
    a1 = int(gd.get('adj1', 'val 16200000').split()[-1]) / 60000
    a2 = int(gd.get('adj2', 'val 0').split()[-1]) / 60000
    rx, ry = w / 2, h / 2
    def pt(a):
        t = math.radians(a)
        return rx + rx * math.cos(t), ry + ry * math.sin(t)
    sweep = (a2 - a1) % 360
    (sx, sy), (ex, ey) = pt(a1), pt(a2)
    large = 1 if sweep > 180 else 0
    stroke = f'stroke="{li["color"]}" stroke-width="{fmt(li["w"])}"' if li else 'stroke="none"'
    return (f'<svg class="s" style="left:{fmt(x)}px;top:{fmt(y)}px;width:{fmt(w)}px;height:{fmt(h)}px;overflow:visible" viewBox="0 0 {fmt(w)} {fmt(h)}">'
            f'<path d="M{fmt(sx)} {fmt(sy)}A{fmt(rx)} {fmt(ry)} 0 {large} 1 {fmt(ex)} {fmt(ey)}" fill="none" {stroke}/></svg>')

def svg_cust(sb, g, spPr, li, fill):
    x, y, w, h = sb
    parts = []
    for path in spPr.iter(A + 'path'):
        pw = int(path.get('w', 0)) or 1
        ph = int(path.get('h', 0)) or 1
        d = []
        for cmd in path:
            t = cmd.tag.replace(A, '')
            pts = [(int(q.get('x')) / pw * w, int(q.get('y')) / ph * h) for q in cmd.findall(A + 'pt')]
            if t == 'moveTo': d.append('M%s %s' % tuple(map(fmt, pts[0])))
            elif t == 'lnTo': d.append('L%s %s' % tuple(map(fmt, pts[0])))
            elif t == 'cubicBezTo': d.append('C' + ' '.join('%s %s' % tuple(map(fmt, q)) for q in pts))
            elif t == 'quadBezTo': d.append('Q' + ' '.join('%s %s' % tuple(map(fmt, q)) for q in pts))
            elif t == 'close': d.append('Z')
        f = fill if (fill and path.get('fill') != 'none') else 'none'
        stroke = f'stroke="{li["color"]}" stroke-width="{fmt(li["w"])}"' if li else ''
        parts.append(f'<path d="{"".join(d)}" fill="{f}" {stroke}/>')
    tr = []
    if g['flipH']: tr.append('scaleX(-1)')
    if g['flipV']: tr.append('scaleY(-1)')
    if g['rot']: tr.append(f'rotate({fmt(g["rot"])}deg)')
    trs = f';transform:{" ".join(tr)}' if tr else ''
    return (f'<svg class="s" style="left:{fmt(x)}px;top:{fmt(y)}px;width:{fmt(w)}px;height:{fmt(h)}px;overflow:visible{trs}" '
            f'viewBox="0 0 {fmt(w)} {fmt(h)}">{"".join(parts)}</svg>')

def render_shapes(tree, xf, part, rels, ctx):
    out = []
    for el in tree:
        tag = el.tag.replace(P, '')
        if tag == 'grpSp':
            gsp = el.find(P + 'grpSpPr')
            out.extend(render_shapes(el, xf.child(gsp), part, rels, ctx))
        elif tag in ('sp', 'cxnSp'):
            spPr = el.find(P + 'spPr')
            g = get_xfrm(spPr)
            if g is None:
                continue
            style, sb = box_style(xf, g)
            geom_el = spPr.find(A + 'prstGeom')
            geom = geom_el.get('prst') if geom_el is not None else ('cust' if spPr.find(A + 'custGeom') is not None else 'rect')
            fill = fill_css(spPr)
            li = line_info(spPr)
            txBody = el.find(P + 'txBody')
            inner, text, fsz = ('', '', 0)
            if txBody is not None:
                inner, text, fsz = text_html(txBody, rels)
                if PAGE_NUM.match(text) and not fill:
                    continue  # stale baked-in page number; the engine shows live numbers
                if text:
                    ctx['texts'].append((fsz, sb[1], text))
            if tag == 'cxnSp' or geom in ('line', 'straightConnector1', 'bentConnector2', 'bentConnector3'):
                if li: out.append(svg_line(sb, g, li))
                continue
            if geom == 'arc':
                out.append(svg_arc(sb, g, spPr, li, fill)); continue
            if geom == 'cust':
                out.append(svg_cust(sb, g, spPr, li, fill))
                if not text: continue
                fill = None; li = None
            if not fill and not li and not text:
                continue
            st = [style]
            if fill: st.append('background:' + fill)
            if li:
                st.append(f'border:{fmt(li["w"])}px {"dashed" if li["dashed"] else "solid"} {li["color"]}')
            if geom == 'ellipse': st.append('border-radius:50%')
            elif geom == 'roundRect': st.append('border-radius:14px')
            shd = shadow_css(spPr)
            if shd: st.append(shd)
            out.append(f'<div class="s" style="{";".join(st)}">{inner if text else ""}</div>')
        elif tag == 'pic':
            spPr = el.find(P + 'spPr')
            g = get_xfrm(spPr)
            if g is None:
                continue
            style, sb = box_style(xf, g)
            blip = el.find(f'{P}blipFill/{A}blip')
            rid = blip.get(R + 'embed') if blip is not None else None
            if not rid or rid not in part.rels:
                continue
            ipart = part.related_part(rid)
            src = rect = el.find(f'{P}blipFill/{A}srcRect')
            l = t = r_ = b = 0
            if rect is not None:
                l, t, r_, b = (int(rect.get(k, 0)) / 100000 for k in ('l', 't', 'r', 'b'))
            vw = sb[2] / max(0.01, 1 - l - r_)
            vh = sb[3] / max(0.01, 1 - t - b)
            try:
                url = export_image(ipart, vw, vh)
            except Exception as e:
                print('image fail', e)
                continue
            st = [style]
            geom_el = spPr.find(A + 'prstGeom')
            if geom_el is not None and geom_el.get('prst') == 'ellipse':
                st.append('border-radius:50%')
            li = line_info(spPr)
            if li: st.append(f'outline:{fmt(li["w"])}px solid {li["color"]}')
            alt = html.escape(el.find(f'{P}nvPicPr/{P}cNvPr').get('descr') or '', quote=True)
            if l or t or r_ or b:
                img = (f'<img src="{url}" alt="{alt}" decoding="async" style="position:absolute;left:{fmt(-l * vw)}px;'
                       f'top:{fmt(-t * vh)}px;width:{fmt(vw)}px;height:{fmt(vh)}px;max-width:none">')
            else:
                img = f'<img src="{url}" alt="{alt}" decoding="async" style="width:100%;height:100%">'
            logo = ' logo' if (url in alpha_urls and sb[2] < 400 and sb[3] < 400) else ''
            out.append(f'<div class="s pic{logo}" style="{";".join(st)}">{img}</div>')
    return out

# ---------------------------------------------------------------- slides
def slide_bg(slide):
    for holder in (slide, slide.slide_layout, slide.slide_layout.slide_master):
        bg = holder._element.find(f'{P}cSld/{P}bg')
        if bg is not None:
            sf = bg.find(f'{P}bgPr/{A}solidFill')
            if sf is not None:
                c = color_of(sf)
                if c: return c[0]
    return 'FFFFFF'

def slugify(s):
    s = re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
    return '-'.join(s.split('-')[:6]) or 'slide'

def notes_of(slide):
    if not slide.has_notes_slide:
        return ''
    t = slide.notes_slide.notes_text_frame.text if slide.notes_slide.notes_text_frame else ''
    t = t.replace('\x0b', '\n').strip()
    if not t:
        return ''
    paras = [p.strip() for p in re.split(r'\n+', t) if p.strip()]
    return ''.join(f'<p>{html.escape(p)}</p>' for p in paras)

os.makedirs(os.path.join(OUT, 'slides'), exist_ok=True)
manifest = []
for idx, slide in enumerate(prs.slides, 1):
    hidden = slide._element.get('show') == '0'
    part = slide.part
    rels = {rid: r.target_ref for rid, r in part.rels.items() if r.is_external}
    bg = slide_bg(slide)
    kind = 'night' if luminance(bg) < 0.35 else 'paper'
    ctx = {'texts': []}
    tree = slide._element.find(f'{P}cSld/{P}spTree')
    body = render_shapes(tree, Xf(), part, rels, ctx)
    texts = sorted(ctx['texts'], key=lambda t: (-t[0], t[1]))
    title = texts[0][2].split('\n')[0].strip() if texts else ''
    if len(title) < 3 and len(texts) > 1:
        title = texts[1][2].split('\n')[0].strip()
    title = title[:90] or f'Slide {idx}'
    fname = f'{PREFIX or "s"}{idx:03d}-{slugify(title)}.html'
    notes = notes_of(slide)
    html_out = (f'<section class="slide canvas {kind}" data-title="{html.escape(title, quote=True)}" '
                f'style="--slide-bg:var(--f-{bg},#{bg})">\n'
                + '\n'.join(body) +
                (f'\n<aside class="notes">{notes}</aside>' if notes else '') +
                '\n</section>\n')
    with open(os.path.join(OUT, 'slides', fname), 'w') as f:
        f.write(f'<!-- Converted from slide {idx} of {os.path.basename(SRC)} -->\n' + html_out)
    manifest.append({'file': fname, 'hidden': hidden, 'title': title, 'orig': idx})
    if not PREFIX:
        print(idx, 'H' if hidden else ' ', kind, title[:60])

if PREFIX:
    print('Converted', len(manifest), 'slides. Paste these lines into slides/manifest.js where they belong:\n')
    for e in manifest:
        h = ', hidden: true' if e['hidden'] else ''
        print(f"  {{ file: {json.dumps(e['file'])}{h} }},".ljust(70) + f" // {e['title'][:50]}")
else:
    with open(os.path.join(OUT, 'manifest.json'), 'w') as f:
        json.dump(manifest, f, indent=1)
