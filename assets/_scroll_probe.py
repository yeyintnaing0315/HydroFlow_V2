from PIL import Image

im = Image.open(r"C:\Users\Huawei\.cursor\projects\d-Ai-Project-HydroFlow-V2\assets\inventory-scroll-check.png").convert("RGB")
w, h = im.size
bright = []
for y in range(h):
    for x in range(w):
        p = im.getpixel((x, y))
        if p[0] > 90 and p[1] > 100:
            bright.append((x, y, p))
print("bright count", len(bright))
if bright:
    xs = sorted({b[0] for b in bright})
    ys = [b[1] for b in bright]
    print("x range", min(xs), max(xs), "y range", min(ys), max(ys))
    print("sample", bright[:8])
# rightmost 20 columns average
for x in range(w - 20, w):
    rs = gs = bs = 0
    for y in range(h):
        p = im.getpixel((x, y))
        rs += p[0]
        gs += p[1]
        bs += p[2]
    print(x, round(rs / h, 1), round(gs / h, 1), round(bs / h, 1))
