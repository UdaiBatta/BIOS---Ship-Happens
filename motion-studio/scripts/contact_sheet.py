# Contact sheet: one frame per story beat, all three formats from the same timeline.
import sys
from PIL import Image, ImageDraw, ImageFont
BEATS = [('01  HOOK', 'kinetic type', 2.45), ('02  PRODUCT', 'UI assembles', 6.40), ('03  FEATURE', 'orbit 3D hands', 9.00),
         ('04  FEATURE', 'scrub timeline', 11.60), ('05  FEATURE', 'jump to problem', 14.90), ('06  PROOF', '239 tests passed', 17.50)]
FMTS = [('9x16', 1080, 1920), ('1x1', 1080, 1080), ('16x9', 1920, 1080)]
B = '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'
R = '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf'
MONO = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
colw, gap, pad = 300, 24, 60
rowh = {'9x16': int(colw * 1920 / 1080), '1x1': colw, '16x9': int(colw * 1080 / 1920)}
Wd = pad * 2 + 90 + len(BEATS) * colw + (len(BEATS) - 1) * gap
Hd = pad + 150 + sum(rowh.values()) + gap * 3 + 40 + 60
S = Image.new('RGB', (Wd, Hd), (13, 13, 13))
d = ImageDraw.Draw(S)
d.text((pad, pad - 10), 'MOTIONIQ', font=ImageFont.truetype(B, 44), fill=(240, 239, 236))
d.rectangle([pad, pad + 46, pad + 110, pad + 51], fill=(217, 89, 38)); d.rectangle([pad + 114, pad + 46, pad + 224, pad + 51], fill=(57, 135, 229))
d.text((pad + 260, pad), 'Showreel · contact sheet · one frame per beat · 20 s @ 120 BPM · same timeline in 9:16, 1:1, 16:9',
       font=ImageFont.truetype(R, 22), fill=(195, 194, 183))
y = pad + 110
x0 = pad + 90
for i, (b, sub, t) in enumerate(BEATS):
    x = x0 + i * (colw + gap)
    d.text((x, y - 4), b, font=ImageFont.truetype(B, 22), fill=(240, 239, 236))
    d.text((x, y + 22), f'{sub} · t={t:.2f}s', font=ImageFont.truetype(MONO, 15), fill=(137, 135, 129))
y += 60
for fmt, w, h in FMTS:
    d.text((pad, y + rowh[fmt] // 2 - 10), fmt.replace('x', ':'), font=ImageFont.truetype(MONO, 22), fill=(195, 194, 183))
    for i, (_, _, t) in enumerate(BEATS):
        im = Image.open(f'build/sheet/{fmt}_{t:.3f}.png').convert('RGB').resize((colw, rowh[fmt]), Image.LANCZOS)
        x = x0 + i * (colw + gap)
        S.paste(im, (x, y))
        d.rectangle([x - 1, y - 1, x + colw, y + rowh[fmt]], outline=(60, 60, 58))
    y += rowh[fmt] + gap
d.text((pad, Hd - 50), 'All UI is real: Playwright captures of frontend/prototype/index.html (synthetic demo data). Number: README verification line, 1 Nov 2026.',
       font=ImageFont.truetype(R, 18), fill=(137, 135, 129))
S.save(sys.argv[1])
print(sys.argv[1], S.size)
