import json, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
t = json.loads((root / 'comp/timeline.json').read_text())
m = json.loads((root / 'assets/ui/manifest.json').read_text())
(root / 'comp/data.js').write_text('window.TL=' + json.dumps(t) + ';\nwindow.MANIFEST=' + json.dumps(m) + ';\n')
print('data.js written')
