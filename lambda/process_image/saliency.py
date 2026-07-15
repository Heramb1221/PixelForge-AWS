"""
lambda/process_image/saliency.py
----------------------------------
A lightweight, dependency-minimal saliency estimator used for "smart
crop": when an image must be cropped to a new aspect ratio, naive
center-cropping often cuts off the subject. Instead we estimate which
region of the image is visually most "interesting" (highest local
edge/gradient energy - faces, text, and high-contrast subjects all
score highly) and center the crop window on that region.

This intentionally avoids pulling in a full ML model (no extra Lambda
layer, no GPU, stays comfortably within the Lambda free tier's compute
budget) while still producing meaningfully better crops than a plain
center-crop on typical photos.
"""
import logging

from PIL import Image, ImageFilter
import numpy as np

logger = logging.getLogger(__name__)


def _edge_energy_map(image: Image.Image, downscale_to: int = 256) -> np.ndarray:
    """
    Returns a 2D numpy array (same aspect ratio as the input, downscaled)
    where each value approximates local edge/gradient energy.
    """
    working = image.convert("L")

    # Downscale for speed; saliency doesn't need full resolution.
    w, h = working.size
    scale = downscale_to / max(w, h)
    if scale < 1.0:
        working = working.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BILINEAR)

    edges = working.filter(ImageFilter.FIND_EDGES)
    arr = np.asarray(edges, dtype=np.float32)

    # Light blur so the energy map is smooth (avoids anchoring on single
    # noisy pixels) while still highlighting genuine high-contrast regions.
    blurred = Image.fromarray(arr).filter(ImageFilter.GaussianBlur(radius=3))
    return np.asarray(blurred, dtype=np.float32)


def find_focal_point(image: Image.Image):
    """
    Returns (fx, fy) as fractions (0.0-1.0) of image width/height
    indicating the estimated center of visual interest.
    """
    try:
        energy = _edge_energy_map(image)
        total = energy.sum()
        if total <= 0:
            return 0.5, 0.5  # flat/blank image - fall back to center

        h, w = energy.shape
        y_indices, x_indices = np.indices((h, w))
        fx = float((x_indices * energy).sum() / total) / w
        fy = float((y_indices * energy).sum() / total) / h

        # Clamp defensively - centroid math can't leave [0,1] but be safe
        # against NaN from degenerate images.
        fx = min(max(fx, 0.0), 1.0) if fx == fx else 0.5
        fy = min(max(fy, 0.0), 1.0) if fy == fy else 0.5
        return fx, fy
    except Exception as exc:
        logger.warning("Saliency detection failed, falling back to center crop: %s", exc)
        return 0.5, 0.5


def compute_smart_crop_box(image_size, target_aspect_ratio, focal_point):
    """
    Given the source image size, a target aspect ratio (w/h), and a focal
    point (fx, fy) as fractions, return a crop box (left, top, right, bottom)
    that has the target aspect ratio, fits within the source image, and is
    centered on the focal point as closely as possible.
    """
    src_w, src_h = image_size
    src_aspect = src_w / src_h

    if src_aspect > target_aspect_ratio:
        # Source is relatively wider than target -> crop width
        crop_h = src_h
        crop_w = int(round(crop_h * target_aspect_ratio))
    else:
        # Source is relatively taller than target -> crop height
        crop_w = src_w
        crop_h = int(round(crop_w / target_aspect_ratio))

    crop_w = min(crop_w, src_w)
    crop_h = min(crop_h, src_h)

    fx, fy = focal_point
    center_x = fx * src_w
    center_y = fy * src_h

    left = int(round(center_x - crop_w / 2))
    top = int(round(center_y - crop_h / 2))

    # Clamp so the crop box stays fully inside the source image.
    left = max(0, min(left, src_w - crop_w))
    top = max(0, min(top, src_h - crop_h))

    return left, top, left + crop_w, top + crop_h
