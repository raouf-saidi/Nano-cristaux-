import re
import numpy as np
import pandas as pd
import cv2

from skimage import color, util, exposure, measure, morphology
from skimage.morphology import (
    disk, square, remove_small_objects, remove_small_holes,
    binary_opening, binary_closing
)
from skimage.measure import label, regionprops_table


# =========================
# CONFIG (tu peux ajuster)
# =========================

MAG_MIN = 200
MAG_MAX = 2000

MIN_LAPLACIAN_VAR = 40.0
MIN_CONTRAST = 0.12

ADAPT_BLOCK = 51
ADAPT_C = 2
MIN_CRYSTAL_SIZE = 30
MIN_HOLE_AREA = 30
OPEN_R, CLOSE_R = 1, 2

N_GRAINS_KEEP = 3
FRACTION_MIN_GRAIN = 0.01
BG_OPEN, BG_CLOSE = 5, 7

R_INFLUENCE = 4
R_TOUCH = 2

AR_NEEDLE = 3.0
CIRC_SPH = 0.75
SOLID_MIN = 0.80

MAX_COVERAGE_ALL = 0.85
MIN_CRYSTALS_OK = 10

BR_MIN_N = 1
BR_MIN_COV = 0.01
BR_MIN_PCT = 0.01


# =========================
# UTILITAIRES
# =========================

def laplacian_var(gray_u8: np.ndarray) -> float:
    return cv2.Laplacian(gray_u8, cv2.CV_64F).var()


def parse_mag_from_filename(fname: str):
    m = re.search(r'(\d{2,5})\s*[xX]', fname)
    if m:
        return int(m.group(1))
    m = re.search(r'mag[_-]?(\d{2,5})', fname, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def decode_image_bytes_to_gray_float(image_bytes: bytes) -> np.ndarray:
    """
    Decode bytes -> image -> grayscale float [0..1]
    """
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("Impossible de décoder l'image (format invalide ou bytes corrompus).")

    # Cas multi-canaux (BGR/BGRA)
    if img.ndim == 3:
        if img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        img_gray = img

    img_gray_float = util.img_as_float(img_gray)
    return img_gray_float


# =========================
# SEGMENTATION
# =========================

def segment_crystals(img_gray_float: np.ndarray):
    img_eq = exposure.equalize_adapthist(img_gray_float, clip_limit=0.01)
    img_blur = cv2.GaussianBlur((img_eq * 255).astype(np.uint8), (3, 3), 0)

    thr = cv2.adaptiveThreshold(
        img_blur, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV,
        ADAPT_BLOCK, ADAPT_C
    )

    mask = thr.astype(bool)
    mask = remove_small_objects(mask, min_size=MIN_CRYSTAL_SIZE)
    mask = remove_small_holes(mask, area_threshold=MIN_HOLE_AREA)
    mask = binary_opening(mask, disk(OPEN_R))
    mask = binary_closing(mask, disk(CLOSE_R))

    lbl = label(mask)
    return mask, lbl


def segment_big_grains(crystal_mask: np.ndarray):
    background = ~crystal_mask
    bg_smooth = morphology.closing(
        morphology.opening(background, square(BG_OPEN)),
        square(BG_CLOSE)
    )
    bg_lbl_all = label(bg_smooth)

    h, w = crystal_mask.shape
    min_area = int(FRACTION_MIN_GRAIN * (h * w))

    props = measure.regionprops(bg_lbl_all)
    cands = [p for p in props if p.area >= min_area]
    cands = sorted(cands, key=lambda p: p.area, reverse=True)[:N_GRAINS_KEEP]

    big_mask = np.zeros_like(bg_lbl_all, dtype=bool)
    for p in cands:
        big_mask[bg_lbl_all == p.label] = True

    bg_lbl = label(big_mask)
    return bg_lbl


def contact_band_from_grains(bg_lbl: np.ndarray, r_influence: int):
    """
    Bande de contact = pixels où au moins 2 grains dilatés se chevauchent.
    IMPORTANT: on ne retire PAS les cristaux de cette bande.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r_influence + 1, 2 * r_influence + 1))
    grain_ids = [lab for lab in np.unique(bg_lbl) if lab != 0]

    overlap = np.zeros_like(bg_lbl, dtype=np.uint8)
    for gid in grain_ids:
        g = (bg_lbl == gid).astype(np.uint8)
        g_dil = cv2.dilate(g, kernel) > 0
        overlap = np.clip(overlap + g_dil.astype(np.uint8), 0, 255)

    return (overlap >= 2)


def bridging_labels_fixed(lbl_cr: np.ndarray, bg_lbl: np.ndarray, contact_band: np.ndarray, r_touch: int):
    """
    Cristal pontant:
    - touche (par proximité) au moins 2 grains (test via dilatation des grains)
    - ET intersecte la bande de contact inter-grains
    """
    grain_ids = [lab for lab in np.unique(bg_lbl) if lab != 0]
    if not grain_ids or lbl_cr.max() == 0:
        return []

    kernel_touch = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r_touch + 1, 2 * r_touch + 1))

    dilated_grains = {}
    for gid in grain_ids:
        g = (bg_lbl == gid).astype(np.uint8)
        dilated_grains[gid] = (cv2.dilate(g, kernel_touch) > 0)

    br = []
    for region in measure.regionprops(lbl_cr):
        coords = np.array(region.coords)
        rr, cc = coords[:, 0], coords[:, 1]

        touched = 0
        for gid in grain_ids:
            if np.any(dilated_grains[gid][rr, cc]):
                touched += 1
                if touched >= 2:
                    break

        in_band = np.any(contact_band[rr, cc])

        if (touched >= 2) and in_band:
            br.append(region.label)

    return br


def classify_habits(lbl_cr: np.ndarray):
    props = regionprops_table(
        lbl_cr,
        properties=("label", "area", "perimeter", "major_axis_length", "minor_axis_length", "solidity")
    )
    df = pd.DataFrame(props)
    if df.empty:
        return df

    ar = df["major_axis_length"] / (df["minor_axis_length"] + 1e-6)
    circ = (4 * np.pi * df["area"]) / ((df["perimeter"] + 1e-6) ** 2)

    def rule(i):
        if ar.iloc[i] >= AR_NEEDLE and df["solidity"].iloc[i] >= SOLID_MIN:
            return "needle_like"
        if circ.iloc[i] >= CIRC_SPH and df["solidity"].iloc[i] >= SOLID_MIN:
            return "spherical"
        if 1.2 <= ar.iloc[i] < AR_NEEDLE and df["solidity"].iloc[i] >= 0.90 and circ.iloc[i] < CIRC_SPH:
            return "blocky"
        return "other"

    df["aspect_ratio"] = ar
    df["circularity"] = circ
    df["habit"] = [rule(i) for i in range(len(df))]
    return df


# =========================
# OVERLAY (retour bytes PNG)
# =========================

def build_overlay_png_bytes(img_gray_float, lbl_cr, br_labels, contact_band, bg_lbl) -> bytes:
    overlay = cv2.cvtColor((img_gray_float * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)

    # Tous cristaux en cyan
    for region in measure.regionprops(lbl_cr):
        rrcc = region.coords
        for (r, c) in rrcc:
            overlay[r, c] = overlay[r, c] * 0.4 + np.array((255, 255, 0)) * 0.6

    # Pontants en magenta
    br_set = set(br_labels)
    for region in measure.regionprops(lbl_cr):
        if region.label in br_set:
            rrcc = region.coords
            for (r, c) in rrcc:
                overlay[r, c] = overlay[r, c] * 0.4 + np.array((255, 0, 255)) * 0.6

    # Bande contact en vert
    overlay[contact_band] = (0, 255, 0)

    # Contours grains en rouge
    edges = cv2.Canny((bg_lbl > 0).astype(np.uint8) * 255, 50, 150)
    overlay[edges > 0] = (0, 0, 255)

    ok, buf = cv2.imencode(".png", overlay)
    if not ok:
        raise RuntimeError("Impossible d'encoder l'overlay en PNG.")
    return buf.tobytes()


# =========================
# ANALYSE (bytes)
# =========================

def analyze_image_bytes(image_bytes: bytes, filename: str = "image.png", mag_value=None, write_debug=False):
    """
    Retourne:
      - metrics: dict
      - overlay_png_bytes: bytes (PNG)
    """
    img_gray = decode_image_bytes_to_gray_float(image_bytes)

    # mag
    mag = mag_value if mag_value is not None else parse_mag_from_filename(filename)
    zoom_ok = (mag is not None) and (MAG_MIN <= mag <= MAG_MAX)

    # qualité
    gray_u8 = (img_gray * 255).astype(np.uint8)
    sharp = laplacian_var(gray_u8)
    contrast = float(img_gray.max() - img_gray.min())
    quality_ok = (sharp >= MIN_LAPLACIAN_VAR) and (contrast >= MIN_CONTRAST)

    # cristaux
    crystal_mask, lbl_cr = segment_crystals(img_gray)
    n_total = int(lbl_cr.max())
    coverage_all = float(crystal_mask.sum()) / crystal_mask.size
    segm_ok = (n_total >= MIN_CRYSTALS_OK) and (coverage_all <= MAX_COVERAGE_ALL)

    # grains
    bg_lbl = segment_big_grains(crystal_mask)
    n_grains = len([x for x in np.unique(bg_lbl) if x != 0])
    grains_ok = (n_grains >= 2)

    good_image = zoom_ok and quality_ok and segm_ok and grains_ok

    # Overlay “de base” si mauvaise image (optionnel mais utile côté front)
    # On met juste contour grains / mask cristaux si possible
    overlay_bytes = b""

    if not good_image:
        reasons = []
        if mag is None:
            reasons.append("mag_inconnu")
        elif not zoom_ok:
            reasons.append("zoom_hors_plage")
        if not quality_ok:
            reasons.append("qualite_insuffisante")
        if not segm_ok:
            reasons.append("segmentation_cristaux_suspecte")
        if not grains_ok:
            reasons.append("moins_de_2_grains")

        # on tente quand même un overlay simple (si segmentations OK partiellement)
        try:
            contact_band = contact_band_from_grains(bg_lbl, r_influence=R_INFLUENCE) if n_grains >= 1 else np.zeros_like(bg_lbl, dtype=bool)
            overlay_bytes = build_overlay_png_bytes(img_gray, lbl_cr, [], contact_band, bg_lbl)
        except Exception:
            overlay_bytes = b""

        return {
            "image": filename,
            "mag": mag,
            "good_image": False,
            "reasons": ";".join(reasons),
            "sharpness_laplacian_var": float(sharp),
            "contrast_range": float(contrast),
            "n_grains": int(n_grains),
            "n_cristaux_total": int(n_total),
            "coverage_all": float(coverage_all),
        }, overlay_bytes

    # bande de contact + pontage
    contact_band = contact_band_from_grains(bg_lbl, r_influence=R_INFLUENCE)
    br_labels = bridging_labels_fixed(lbl_cr, bg_lbl, contact_band, r_touch=R_TOUCH)

    n_bridge = len(br_labels)
    pct_bridge = (n_bridge / n_total) if n_total > 0 else 0.0
    bridging_mask = np.isin(lbl_cr, br_labels)
    coverage_br = float(bridging_mask.sum()) / bridging_mask.size

    # densités
    h, w = img_gray.shape
    area_px = h * w
    dens_all_Mpx = (n_total / area_px) * 1e6
    dens_br_Mpx = (n_bridge / area_px) * 1e6

    # morphologies
    df_h = classify_habits(lbl_cr)
    counts_all = df_h["habit"].value_counts().to_dict() if not df_h.empty else {}
    pct_needle = counts_all.get("needle_like", 0) / n_total if n_total else 0.0
    pct_blocky = counts_all.get("blocky", 0) / n_total if n_total else 0.0
    pct_sph = counts_all.get("spherical", 0) / n_total if n_total else 0.0
    pct_other = counts_all.get("other", 0) / n_total if n_total else 0.0

    if n_bridge and not df_h.empty:
        df_br = df_h[df_h["label"].isin(br_labels)]
        counts_br = df_br["habit"].value_counts().to_dict()
        pct_br_needle = counts_br.get("needle_like", 0) / n_bridge
        pct_br_blocky = counts_br.get("blocky", 0) / n_bridge
        pct_br_sph = counts_br.get("spherical", 0) / n_bridge
        pct_br_other = counts_br.get("other", 0) / n_bridge
    else:
        pct_br_needle = pct_br_blocky = pct_br_sph = pct_br_other = 0.0

    # inutiles + scores
    n_useless = n_total - n_bridge
    pct_useless = 1.0 - pct_bridge
    coverage_useless = max(0.0, coverage_all - coverage_br)

    eps = 1e-6
    useless_to_useful_ratio = coverage_useless / (coverage_br + eps)
    useful_fraction_of_deposit = coverage_br / (coverage_all + eps)

    bridging_success = (n_bridge >= BR_MIN_N) and (coverage_br >= BR_MIN_COV) and (pct_bridge >= BR_MIN_PCT)
    bridging_strength_score = 0.5 * pct_bridge + 0.5 * useful_fraction_of_deposit

    # overlay final
    overlay_bytes = build_overlay_png_bytes(img_gray, lbl_cr, br_labels, contact_band, bg_lbl)

    metrics = {
        "image": filename,
        "mag": mag,
        "good_image": True,
        "reasons": "",

        # qualité
        "sharpness_laplacian_var": float(sharp),
        "contrast_range": float(contrast),

        # grains
        "n_grains": int(n_grains),

        # cristaux
        "n_cristaux_total": int(n_total),
        "coverage_all": float(coverage_all),
        "density_all_per_Mpx": float(dens_all_Mpx),

        # pontage
        "n_cristaux_pontage": int(n_bridge),
        "pct_cristaux_pontage": float(pct_bridge),
        "coverage_bridging": float(coverage_br),
        "density_bridging_per_Mpx": float(dens_br_Mpx),

        # inutiles
        "n_cristaux_inutiles": int(n_useless),
        "pct_cristaux_inutiles": float(pct_useless),
        "coverage_useless": float(coverage_useless),
        "useful_fraction_of_deposit": float(useful_fraction_of_deposit),
        "useless_to_useful_ratio": float(useless_to_useful_ratio),

        # morphologie (tous)
        "pct_needle_like": float(pct_needle),
        "pct_blocky": float(pct_blocky),
        "pct_spherical": float(pct_sph),
        "pct_other": float(pct_other),

        # morphologie (pontants)
        "pct_bridging_needle_like": float(pct_br_needle),
        "pct_bridging_blocky": float(pct_br_blocky),
        "pct_bridging_spherical": float(pct_br_sph),
        "pct_bridging_other": float(pct_br_other),

        # verdict
        "bridging_success": bool(bridging_success),
        "bridging_strength_score": float(bridging_strength_score),
    }

    return metrics, overlay_bytes
