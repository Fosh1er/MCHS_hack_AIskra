import sys, os, subprocess, tempfile
import pymupdf
from PIL import Image, ImageDraw
src, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
prof = tempfile.mkdtemp(prefix="lo_")
subprocess.run(["/Applications/LibreOffice.app/Contents/MacOS/soffice", f"-env:UserInstallation=file://{prof}", "--headless", "--convert-to", "pdf", "--outdir", out, src], check=True, capture_output=True)
pdf = os.path.join(out, os.path.splitext(os.path.basename(src))[0] + ".pdf")
d = pymupdf.open(pdf); files = []
for i, p in enumerate(d, 1):
    fn = os.path.join(out, f"s{i:02d}.png"); p.get_pixmap(dpi=90).save(fn); files.append(fn)
W = 460
for g in range(0, len(files), 9):
    ims = [Image.open(f) for f in files[g:g+9]]; h = int(W * ims[0].height / ims[0].width)
    G = Image.new("RGB", (3*W+40, ((len(ims)+2)//3)*(h+26)+10), "white"); dr = ImageDraw.Draw(G)
    for k, im in enumerate(ims):
        x = 10+(k%3)*(W+10); y = 10+(k//3)*(h+26); G.paste(im.resize((W, h)), (x, y+18)); dr.text((x, y+3), f"Slide {g+k+1}", fill="black")
    G.save(os.path.join(out, f"grid{g//9+1}.jpg"), quality=85)
print(pdf, len(files))
