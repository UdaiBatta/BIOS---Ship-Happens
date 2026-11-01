"""Film-grain tiles for the comp overlay (comp/grain_0..5.png). Generated, not committed (repo ignores *.png)."""
import pathlib
import numpy as np
from PIL import Image
root = pathlib.Path(__file__).resolve().parent.parent
rng = np.random.default_rng(7)
for i in range(6):
    Image.fromarray(rng.normal(128, 40, (384, 384)).clip(0, 255).astype('uint8'), 'L').save(root / f'comp/grain_{i}.png')
print('grain tiles written')
