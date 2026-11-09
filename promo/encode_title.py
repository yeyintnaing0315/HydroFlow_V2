import cv2
from pathlib import Path

folder = Path(r"D:\Ai_Project\HydroFlow_V2\promo\title\frames")
out_path = Path(r"D:\Ai_Project\HydroFlow_V2\promo\HydroFlow_title_1080p.mp4")
fps = 30
size = (1920, 1080)
frames = sorted(folder.glob("f*.png"))
if not frames:
    raise SystemExit(f"no frames in {folder}")

writer = None
for codec in ("avc1", "H264", "mp4v"):
    candidate = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*codec), fps, size)
    if candidate.isOpened():
        writer = candidate
        print("codec", codec)
        break
    candidate.release()
if writer is None:
    raise SystemExit("no video codec")

for frame in frames:
    image = cv2.imread(str(frame))
    if image is None:
        raise SystemExit(f"missing {frame.name}")
    if (image.shape[1], image.shape[0]) != size:
        raise SystemExit(f"{frame.name} is {image.shape[1]}x{image.shape[0]}, expected 1920x1080")
    writer.write(image)
writer.release()
print("done", out_path, "frames", len(frames), "seconds", len(frames) / fps)
