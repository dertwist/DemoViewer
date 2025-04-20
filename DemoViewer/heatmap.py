def calc_heatmap_np(footsteps, w, h):
    import numpy as np
    heat = np.zeros((h, w), dtype=np.float32)
    if not footsteps:
        return heat
    arr = np.array(footsteps, dtype=np.float32)
    ix = np.round(arr[:, 1]).astype(int)
    iy = np.round(arr[:, 2]).astype(int)
    mask = (ix >= 0) & (ix < w) & (iy >= 0) & (iy < h)
    ix = ix[mask]
    iy = iy[mask]
    np.add.at(heat, (iy, ix), 1)
    return heat

def heatmap_to_qimage(
    data, cmap="jet", gamma=1/3.0,
    brightness=0.0, contrast=1.0
):
    import numpy as np
    from matplotlib import colormaps
    from PySide6.QtGui import QImage
    if data.size == 0:
        return QImage(1, 1, QImage.Format_ARGB32_Premultiplied)
    data = np.flipud(data)
    vmax = data.max()
    vmin = data.min()
    if vmax > vmin:
        norm = (data - vmin) / (vmax - vmin)
        norm = norm ** gamma
    else:
        norm = np.zeros_like(data)

    norm = contrast * (norm - 0.5) + 0.5 + brightness
    norm = np.clip(norm, 0, 1)

    try:
        cmap_obj = colormaps.get_cmap(cmap)
    except Exception:
        cmap_obj = colormaps.get_cmap("jet")
    rgba = cmap_obj(norm, bytes=True)
    alpha = (norm * 255).astype(np.uint8)
    rgba[..., 3] = alpha
    h_, w_ = rgba.shape[:2]
    qimg = QImage(rgba.data, w_, h_, rgba.strides[0], QImage.Format_RGBA8888)
    return qimg.copy()