# Build a labelled sheet from stills: python3 scripts/sheet.py <fmt> <out.png> [cols] [thumbW]
import sys, glob, os
from PIL import Image, ImageDraw, ImageFont
fmt, out = sys.argv[1], sys.argv[2]
cols = int(sys.argv[3]) if len(sys.argv) > 3 else 6
tw = int(sys.argv[4]) if len(sys.argv) > 4 else 360
fs = sorted(glob.glob(f'build/stills/{fmt}_*.png'), key=lambda f: float(f.split('_')[-1][:-4]))
ims = [Image.open(f).convert('RGB') for f in fs]
th = int(ims[0].height * tw / ims[0].width)
rows = (len(ims) + cols - 1) // cols
S = Image.new('RGB', (cols * (tw + 10) + 10, rows * (th + 40) + 10), (240, 240, 236))
d = ImageDraw.Draw(S)
font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 16)
for i, (f, im) in enumerate(zip(fs, ims)):
    x, y = 10 + (i % cols) * (tw + 10), 10 + (i // cols) * (th + 40)
    S.paste(im.resize((tw, th), Image.LANCZOS), (x, y))
    d.text((x, y + th + 8), 't = ' + f.split('_')[-1][:-4] + ' s', fill=(30, 30, 30), font=font)
S.save(out)
print(out, S.size)
