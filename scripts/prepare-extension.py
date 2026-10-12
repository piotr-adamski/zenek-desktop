from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[1]/'gnome-extension/zenek@brillnet'
data=(root/'companion.js').read_bytes()
module='companion-'+hashlib.sha256(data).hexdigest()[:16]+'.js'
(root/module).write_bytes(data)
(root/'build.json').write_text(json.dumps({'module':module,'sha256':hashlib.sha256(data).hexdigest()}))
print(module)
