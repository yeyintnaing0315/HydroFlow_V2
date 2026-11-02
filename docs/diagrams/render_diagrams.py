"""Render labeled HydroFlow diagram PNGs."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
INK = (25, 25, 25)
WHITE = (255, 255, 255)
MUTED = (90, 90, 90)

FONT = "C:/Windows/Fonts/segoeui.ttf"
FONT_B = "C:/Windows/Fonts/segoeuib.ttf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_B if bold else FONT, size)


def text_size(draw: ImageDraw.ImageDraw, value: str, face: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), value, font=face)
    return box[2] - box[0], box[3] - box[1]


def center_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    value: str,
    face: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int] = INK,
) -> None:
    left, top, right, bottom = box
    tw, th = text_size(draw, value, face)
    glyph = draw.textbbox((0, 0), value, font=face)
    x = left + (right - left - tw) / 2
    y = top + (bottom - top - th) / 2 - glyph[1]
    draw.text((x, y), value, font=face, fill=fill)


def arrow(draw: ImageDraw.ImageDraw, x1: float, y1: float, x2: float, y2: float, width: int = 3) -> None:
    draw.line((x1, y1, x2, y2), fill=INK, width=width)
    angle = math.atan2(y2 - y1, x2 - x1)
    size = 12
    left = (
        x2 - size * math.cos(angle) + size * 0.45 * math.sin(angle),
        y2 - size * math.sin(angle) - size * 0.45 * math.cos(angle),
    )
    right = (
        x2 - size * math.cos(angle) - size * 0.45 * math.sin(angle),
        y2 - size * math.sin(angle) + size * 0.45 * math.cos(angle),
    )
    draw.polygon([(x2, y2), left, right], fill=INK)


def poly_arrow(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]]) -> None:
    draw.line(points, fill=INK, width=3, joint="curve")
    arrow(draw, points[-2][0], points[-2][1], points[-1][0], points[-1][1])


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, face: ImageFont.FreeTypeFont) -> None:
    draw.rounded_rectangle(box, radius=22, outline=INK, width=3, fill=WHITE)
    center_text(draw, box, label, face)


def rect(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, face: ImageFont.FreeTypeFont) -> None:
    draw.rectangle(box, outline=INK, width=3, fill=WHITE)
    center_text(draw, box, label, face)


def para(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, face: ImageFont.FreeTypeFont) -> None:
    left, top, right, bottom = box
    skew = 16
    draw.polygon(
        [(left + skew, top), (right, top), (right - skew, bottom), (left, bottom)],
        outline=INK,
        fill=WHITE,
    )
    draw.line([(left + skew, top), (right, top), (right - skew, bottom), (left, bottom), (left + skew, top)], fill=INK, width=3)
    center_text(draw, box, label, face)


def diamond(draw: ImageDraw.ImageDraw, cx: int, cy: int, w: int, h: int, label: str, face: ImageFont.FreeTypeFont) -> None:
    points = [(cx, cy - h // 2), (cx + w // 2, cy), (cx, cy + h // 2), (cx - w // 2, cy)]
    draw.polygon(points, outline=INK, fill=WHITE)
    draw.line(points + [points[0]], fill=INK, width=3)
    center_text(draw, (cx - w // 2, cy - 16, cx + w // 2, cy + 16), label, face)


def cylinder(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, face: ImageFont.FreeTypeFont) -> None:
    left, top, right, bottom = box
    ry = 14
    draw.rectangle((left, top + ry, right, bottom - ry), fill=WHITE, outline=WHITE)
    draw.ellipse((left, top, right, top + ry * 2), outline=INK, width=3, fill=WHITE)
    draw.rectangle((left, top + ry, right, bottom - ry), outline=INK, width=3, fill=WHITE)
    draw.arc((left, bottom - ry * 2, right, bottom), 0, 180, fill=INK, width=3)
    draw.line((left, top + ry, left, bottom - ry), fill=INK, width=3)
    draw.line((right, top + ry, right, bottom - ry), fill=INK, width=3)
    draw.ellipse((left, top, right, top + ry * 2), outline=INK, width=3, fill=WHITE)
    center_text(draw, (left, top + 8, right, bottom), label, face)


def title_block(draw: ImageDraw.ImageDraw, width: int, title: str, subtitle: str) -> int:
    draw.text((48, 28), title, font=font(40, True), fill=INK)
    draw.text((48, 80), subtitle, font=font(22), fill=MUTED)
    draw.line((48, 122, width - 48, 122), fill=(210, 210, 210), width=2)
    return 148


def draw_flow() -> Image.Image:
    width, height = 1680, 1180
    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)
    title_block(draw, width, "System flow", "HydroFlow admin")
    label = font(22)
    small = font(18)

    pad, gap = 36, 20
    col_w = (width - pad * 2 - gap * 3) // 4
    centers = [pad + col_w // 2 + i * (col_w + gap) for i in range(4)]
    box_w, box_h, vgap = 250, 54, 34
    top = 250

    def box_at(cx: int, y: int) -> tuple[int, int, int, int]:
        return (cx - box_w // 2, y, cx + box_w // 2, y + box_h)

    lanes = [
        [("io", "View map"), ("p", "Select place"), ("p", "Request outlook"), ("io", "Show risk"), ("p", "Plan route")],
        [("io", "View census"), ("p", "Request help"), ("io", "Show plan")],
        [("io", "View stock"), ("d", "Scan?"), ("split", ""), ("p", "Save stock")],
        [("p", "Start run"), ("p", "Fetch data"), ("p", "Save risk"), ("io", "View run")],
    ]
    bottoms: list[int] = []
    last_boxes: list[tuple[int, int, int, int]] = []
    first_boxes: list[tuple[int, int, int, int]] = []

    for index, steps in enumerate(lanes):
        cx = centers[index]
        y = top
        prev = None
        first = None
        for kind, name in steps:
            if kind == "split":
                sw, sh = 112, 48
                side_y = prev[3] + 28
                left_cx = cx - 68
                right_cx = cx + 68
                left = (left_cx - sw // 2, side_y, left_cx + sw // 2, side_y + sh)
                right = (right_cx - sw // 2, side_y, right_cx + sw // 2, side_y + sh)
                mid_y = (prev[1] + prev[3]) // 2
                poly_arrow(draw, [(prev[0], mid_y), (prev[0], left[1])])
                poly_arrow(draw, [(prev[2], mid_y), (prev[2], right[1])])
                draw.text((cx - 78, prev[3] + 4), "Yes", font=small, fill=INK)
                draw.text((cx + 46, prev[3] + 4), "No", font=small, fill=INK)
                rect(draw, left, "Detect", label)
                rect(draw, right, "Manual", label)
                prev = ("split", left_cx, right_cx, side_y + sh, cx)
                y = side_y + sh + vgap
                continue
            if kind == "d":
                diamond(draw, cx, y + 46, 150, 92, name, label)
                node = (cx - 75, y, cx + 75, y + 92)
            elif kind == "io":
                node = box_at(cx, y)
                para(draw, node, name, label)
            else:
                node = box_at(cx, y)
                rect(draw, node, name, label)
            if first is None:
                first = node
            if prev is not None:
                if prev[0] == "split":
                    poly_arrow(draw, [(prev[1], prev[3]), (prev[1], node[1] - 16), (cx - 22, node[1] - 16), (cx - 22, node[1])])
                    poly_arrow(draw, [(prev[2], prev[3]), (prev[2], node[1] - 16), (cx + 22, node[1] - 16), (cx + 22, node[1])])
                else:
                    arrow(draw, cx, prev[3], cx, node[1])
            prev = node
            y = node[3] + vgap
        first_boxes.append(first)
        last_boxes.append(prev if prev[0] != "split" else (cx - box_w // 2, prev[3] - box_h, cx + box_w // 2, prev[3]))
        bottoms.append(prev[3] if prev[0] != "split" else prev[3])

    start = (width // 2 - 70, 156, width // 2 + 70, 200)
    rounded(draw, start, "Start", label)
    arrow(draw, width // 2, 200, width // 2, 214)
    admin_box = draw.textbbox((0, 0), "Admin", font=font(26, True))
    admin_w = admin_box[2] - admin_box[0]
    draw.text(((width - admin_w) / 2, 214), "Admin", font=font(26, True), fill=INK)
    split_y = 248
    draw.line((width // 2, 246, width // 2, split_y), fill=INK, width=3)
    draw.line((centers[0], split_y, centers[3], split_y), fill=INK, width=3)
    for cx, node in zip(centers, first_boxes):
        arrow(draw, cx, split_y, cx, node[1])

    bus_y = max(bottoms) + 36
    draw.line((centers[0], bus_y, centers[3], bus_y), fill=INK, width=3)
    for cx, node in zip(centers, last_boxes):
        draw.line((cx, node[3], cx, bus_y), fill=INK, width=3)
    db = (width // 2 - 80, bus_y + 22, width // 2 + 80, bus_y + 96)
    arrow(draw, width // 2, bus_y, width // 2, db[1])
    cylinder(draw, db, "Database", label)
    stop_y = db[3] + 22
    arrow(draw, width // 2, db[3], width // 2, stop_y)
    rounded(draw, (width // 2 - 70, stop_y, width // 2 + 70, stop_y + 44), "Stop", label)
    return image.crop((0, 0, width, stop_y + 70))


def draw_cases() -> Image.Image:
    width, height = 1100, 760
    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)
    title_block(draw, width, "Use cases", "HydroFlow admin")
    face = font(24)
    names = ["View map", "Request outlook", "Plan route", "Request help", "Manage stock", "Start run"]
    oval_w, oval_h, pitch = 280, 58, 84
    origin_x, origin_y = 180, 180
    for index, name in enumerate(names):
        y = origin_y + index * pitch
        box = (origin_x, y, origin_x + oval_w, y + oval_h)
        draw.ellipse(box, outline=INK, width=3, fill=WHITE)
        center_text(draw, box, name, face)

    first_cy = origin_y + oval_h // 2
    last_cy = origin_y + (len(names) - 1) * pitch + oval_h // 2
    stick_x = origin_x + oval_w + 180
    head_y = (first_cy + last_cy) // 2 - 70
    draw.ellipse((stick_x - 18, head_y, stick_x + 18, head_y + 36), outline=INK, width=3)
    neck = head_y + 36
    draw.line((stick_x, neck, stick_x, neck + 70), fill=INK, width=3)
    draw.line((stick_x - 36, neck + 24, stick_x + 36, neck + 24), fill=INK, width=3)
    draw.line((stick_x, neck + 70, stick_x - 28, neck + 120), fill=INK, width=3)
    draw.line((stick_x, neck + 70, stick_x + 28, neck + 120), fill=INK, width=3)
    meet = (stick_x - 36, neck + 24)
    bend_x = origin_x + oval_w + 36
    for index in range(len(names)):
        cy = origin_y + index * pitch + oval_h // 2
        draw.line([(origin_x + oval_w, cy), (bend_x, cy), meet], fill=INK, width=3)
    admin = "Admin"
    face_b = font(26, True)
    tw, _ = text_size(draw, admin, face_b)
    draw.text((stick_x - tw / 2, neck + 132), admin, font=face_b, fill=INK)
    return image.crop((0, 0, width, neck + 190))


def entity(draw: ImageDraw.ImageDraw, x: int, y: int, title: str, rows: list[tuple[str, str]]) -> tuple[int, int, int, int]:
    width, header, row_h = 360, 42, 34
    height = header + row_h * len(rows)
    box = (x, y, x + width, y + height)
    draw.rectangle(box, outline=INK, width=3, fill=WHITE)
    draw.line((x, y + header, x + width, y + header), fill=INK, width=3)
    split = x + int(width * 0.58)
    draw.line((split, y + header, split, y + height), fill=INK, width=3)
    center_text(draw, (x, y, x + width, y + header), title, font(22, True))
    face = font(18)
    for index, (name, kind) in enumerate(rows):
        top = y + header + index * row_h
        if index:
            draw.line((x, top, x + width, top), fill=INK, width=2)
        draw.text((x + 12, top + 6), name, font=face, fill=INK)
        draw.text((split + 12, top + 6), kind, font=face, fill=INK)
    return box


def crow(draw: ImageDraw.ImageDraw, x: int, y: int, direction: str) -> None:
    if direction == "right":
        draw.line((x - 16, y, x, y - 8), fill=INK, width=3)
        draw.line((x - 16, y, x, y), fill=INK, width=3)
        draw.line((x - 16, y, x, y + 8), fill=INK, width=3)
    elif direction == "left":
        draw.line((x + 16, y, x, y - 8), fill=INK, width=3)
        draw.line((x + 16, y, x, y), fill=INK, width=3)
        draw.line((x + 16, y, x, y + 8), fill=INK, width=3)
    else:
        draw.line((x - 8, y - 16, x - 8, y), fill=INK, width=3)
        draw.line((x, y - 16, x, y), fill=INK, width=3)
        draw.line((x + 8, y - 16, x + 8, y), fill=INK, width=3)


def relate_h(draw: ImageDraw.ImageDraw, one_x: int, many_x: int, y: int, label_text: str, many_on_right: bool) -> None:
    face = font(18)
    tw, th = text_size(draw, label_text, face)
    mid = (one_x + many_x) // 2
    draw.line((one_x, y - 10, one_x, y + 10), fill=INK, width=3)
    draw.line((min(one_x, many_x) + 4, y, mid - tw // 2 - 8, y), fill=INK, width=3)
    draw.line((mid + tw // 2 + 8, y, max(one_x, many_x) - 22, y), fill=INK, width=3)
    circle_x = many_x - 22 if many_on_right else many_x + 22
    draw.ellipse((circle_x - 6, y - 6, circle_x + 6, y + 6), outline=INK, width=3, fill=WHITE)
    crow(draw, many_x, y, "right" if many_on_right else "left")
    glyph = draw.textbbox((0, 0), label_text, font=face)
    draw.text((mid - tw / 2, y - th / 2 - glyph[1]), label_text, font=face, fill=INK)


def relate_v(draw: ImageDraw.ImageDraw, x: int, one_y: int, many_y: int, label_text: str) -> None:
    face = font(18)
    tw, th = text_size(draw, label_text, face)
    mid = (one_y + many_y) // 2
    draw.line((x - 10, one_y, x + 10, one_y), fill=INK, width=3)
    draw.line((x, one_y + 4, x, mid - 14), fill=INK, width=3)
    draw.line((x, mid + 14, x, many_y - 22), fill=INK, width=3)
    draw.ellipse((x - 6, many_y - 28, x + 6, many_y - 16), outline=INK, width=3, fill=WHITE)
    crow(draw, x, many_y, "down")
    glyph = draw.textbbox((0, 0), label_text, font=face)
    draw.rectangle((x - tw // 2 - 4, mid - th // 2 - 2, x + tw // 2 + 4, mid + th // 2 + 2), fill=WHITE)
    draw.text((x - tw / 2, mid - th / 2 - glyph[1]), label_text, font=face, fill=INK)


def draw_er() -> Image.Image:
    width, height = 1500, 1280
    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)
    title_block(draw, width, "ER diagram", "HydroFlow main tables")
    ew = 360
    gap_x = 200
    x1 = (width - (ew * 2 + gap_x)) // 2
    x2 = x1 + ew + gap_x
    area = entity(draw, x1, 170, "Admin area", [("name", "text"), ("level", "int"), ("code", "text")])
    settlement = entity(draw, x2, 170, "Settlement", [("name", "text"), ("lat", "float"), ("lon", "float")])
    relate_h(draw, area[2], settlement[0], (area[1] + area[3]) // 2, "contains", True)
    risk = entity(draw, x1, area[3] + 90, "Risk result", [("level", "text"), ("score", "float"), ("type", "text")])
    run = entity(draw, x2, area[3] + 90, "Job run", [("status", "text"), ("started", "date"), ("attempt", "int")])
    relate_v(draw, (area[0] + area[2]) // 2, area[3], risk[1], "has")
    relate_h(draw, run[0], risk[2], (risk[1] + risk[3]) // 2, "produces", False)
    category = entity(draw, x1, risk[3] + 90, "Category", [("code", "text"), ("name", "text"), ("mode", "text")])
    item = entity(draw, x2, risk[3] + 90, "Item type", [("name", "text"), ("unit", "text"), ("code", "text")])
    relate_h(draw, category[2], item[0], (category[1] + category[3]) // 2, "has", True)
    east = entity(draw, x1, category[3] + 70, "Bago East", [("item", "text"), ("qty", "number"), ("unit", "text")])
    entity(draw, x2, category[3] + 70, "Bago West", [("item", "text"), ("qty", "number"), ("unit", "text")])
    return image.crop((0, 0, width, east[3] + 48))


def main() -> None:
    images = {
        "hydroflow-system-flow.png": draw_flow(),
        "hydroflow-use-cases.png": draw_cases(),
        "hydroflow-er-diagram.png": draw_er(),
    }
    gap = 48
    width = max(image.width for image in images.values())
    height = sum(image.height for image in images.values()) + gap * 2
    sheet = Image.new("RGB", (width, height), WHITE)
    y = 0
    for image in images.values():
        sheet.paste(image, ((width - image.width) // 2, y))
        y += image.height + gap
    images["hydroflow-diagrams.png"] = sheet
    for name, image in images.items():
        image.save(OUT / name, "PNG")
        print(f"{name} {image.width}x{image.height}")


if __name__ == "__main__":
    main()
