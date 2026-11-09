import cv2

frames = [
    ("01-title.png", 12),
    ("02-monsoon.png", 8),
    ("03-office.png", 8),
    ("04-home.png", 6),
    ("05-home-route.png", 8),
    ("06-depots.png", 8),
    ("07-to-prediction.png", 6),
    ("08-map.png", 6),
    ("09-bands.png", 8),
    ("10-inputs.png", 7),
    ("11-not-gauge.png", 6),
    ("12-bago-severe.png", 7),
    ("13-compare-dates.png", 6),
    ("14-plan-button.png", 6),
    ("15-people.png", 7),
    ("16-package.png", 7),
    ("17-illustration.png", 7),
    ("18-route.png", 7),
    ("19-to-stock.png", 6),
    ("20-stock.png", 6),
    ("21-detect.png", 8),
    ("22-confirm.png", 6),
    ("23-workflow.png", 8),
    ("24-close.png", 18),
]
folder = r"D:\Ai_Project\HydroFlow_V2\promo\frames"
out_path = r"D:\Ai_Project\HydroFlow_V2\promo\HydroFlow_V2_promo.mp4"
fps = 30
size = (1920, 1080)
writer = None
for codec in ("avc1", "H264", "mp4v"):
    candidate = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*codec), fps, size)
    if candidate.isOpened():
        writer = candidate
        print("codec", codec)
        break
    candidate.release()
if writer is None:
    raise SystemExit("no video codec")

for name, seconds in frames:
    image = cv2.imread(f"{folder}\\{name}")
    if image is None:
        raise SystemExit(f"missing {name}")
    if (image.shape[1], image.shape[0]) != size:
        image = cv2.resize(image, size)
    for _ in range(seconds * fps):
        writer.write(image)
    print("wrote", name, seconds)
writer.release()
print("done", out_path)
