"""Pure coordinate mapping helpers for Mudra."""


def validate_area(area):
    if len(area) != 4:
        raise ValueError("area must contain LEFT TOP RIGHT BOTTOM")
    left, top, right, bottom = map(float, area)
    if not (0.0 <= left < right <= 1.0):
        raise ValueError("--area requires 0 <= LEFT < RIGHT <= 1")
    if not (0.0 <= top < bottom <= 1.0):
        raise ValueError("--area requires 0 <= TOP < BOTTOM <= 1")
    return left, top, right, bottom


def transform_normalized(x, y, rotate=0, mirror_x=False, mirror_y=False):
    """Rotate clockwise, then mirror, a normalized camera coordinate."""
    x, y = float(x), float(y)
    if rotate == 0:
        tx, ty = x, y
    elif rotate == 90:
        tx, ty = 1.0 - y, x
    elif rotate == 180:
        tx, ty = 1.0 - x, 1.0 - y
    elif rotate == 270:
        tx, ty = y, 1.0 - x
    else:
        raise ValueError("rotate must be one of 0, 90, 180, 270")
    if mirror_x:
        tx = 1.0 - tx
    if mirror_y:
        ty = 1.0 - ty
    return tx, ty


def camera_point_to_screen(px, py, frame_w, frame_h, area,
                           rotate=0, mirror_x=False, mirror_y=False):
    """Map a raw camera pixel into normalized screen coordinates."""
    if frame_w <= 0 or frame_h <= 0:
        raise ValueError("frame dimensions must be positive")
    left, top, right, bottom = validate_area(area)
    x, y = transform_normalized(
        float(px) / float(frame_w), float(py) / float(frame_h),
        rotate, mirror_x, mirror_y)
    sx = (x - left) / (right - left)
    sy = (y - top) / (bottom - top)
    return min(1.0, max(0.0, sx)), min(1.0, max(0.0, sy))
