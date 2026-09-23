import sys
import json
m=json.load(open(sys.argv[1] + '/manifest.json'))
lines=['/* Slide order for the deck.',
' *',
' * Each entry is a file in this folder. The show plays them top to bottom.',
' *   - To insert a slide: add its file here, at the position you want.',
' *   - To hide a slide without deleting it: add  hidden: true',
' *   - To reorder: move lines. File names do not need to match the order.',
' * Press H during the show to include hidden slides.',
' */',
'window.DECK_MANIFEST = [']
for e in m:
    t=e['title'].replace('*/','')
    h=', hidden: true' if e['hidden'] else ''
    lines.append(f"  {{ file: {json.dumps(e['file'])}{h} }},".ljust(78)+f" // {t[:60]}")
lines.append('];')
open(sys.argv[1] + '/slides/manifest.js','w').write('\n'.join(lines)+'\n')
