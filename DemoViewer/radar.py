import os
from PySide6.QtWidgets import QFileDialog, QMessageBox
from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import Qt, QRectF
import os
import tempfile
import vpk
import vdf
from PySide6.QtWidgets import QMessageBox, QInputDialog
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt
import re
from .parser import SESSION_TEMP_FOLDER
from .common import (
    load_qimage_from_path,
    load_radar_info,
    get_workshop_folder,
    get_official_vpk_path,
    fetch_file_from_vpk
)
def session_radar_image_path(map_name, addon):
    safe_map = re.sub(r"[^a-zA-Z0-9_.-]+", "_", map_name or "unknown")
    safe_addon = re.sub(r"[^a-zA-Z0-9_.-]+", "_", addon or "official")
    return os.path.join(SESSION_TEMP_FOLDER, f"radar_{safe_map}_{safe_addon}.png")

class RadarLoader:
    """
    Handles loading and processing of radar images for CS2 maps.
    Supports both official and workshop maps, with caching for performance.
    """

    def __init__(self, parent=None):
        """
        Initialize the RadarLoader.

        Args:
            parent: The parent widget that will display error messages
        """
        self.parent = parent
        self.radar_info = {"pos_x": 0, "pos_y": 0, "scale": 1}

    def load_map_radar(self, map_name, addon=None):
        """
        Load a radar image for the specified map.

        Args:
            map_name: The name of the map to load
            addon: The workshop addon ID if it's a workshop map

        Returns:
            tuple: (radar_image, radar_info, success)
                - radar_image: QImage of the radar
                - radar_info: Dictionary with pos_x, pos_y, scale
                - success: Boolean indicating if loading was successful
        """
        self.radar_info = {"pos_x": 0, "pos_y": 0, "scale": 1}
        radar_img = None

        # Try session cache first
        radar_img_path = session_radar_image_path(map_name, addon)
        if os.path.isfile(radar_img_path):
            radar_img = load_qimage_from_path(radar_img_path)
            if radar_img and not radar_img.isNull():
                # Load radar config
                if not self._load_radar_config(map_name, addon):
                    return None, self.radar_info, False
                return radar_img, self.radar_info, True

        # Determine VPK path
        vpk_path = self._get_vpk_path(map_name, addon)
        if not vpk_path:
            return None, self.radar_info, False

        # Load radar config
        if not self._load_radar_config(map_name, addon):
            return None, self.radar_info, False

        # Load radar image
        radar_img = self._load_radar_image(vpk_path, map_name)

        # Save to session cache for future fast switching
        if radar_img and not radar_img.isNull():
            radar_img.save(radar_img_path, "PNG")
            return radar_img, self.radar_info, True

        # Create fallback image if loading failed
        if not radar_img or radar_img.isNull():
            radar_img = QImage(512, 512, QImage.Format_RGB888)
            radar_img.fill(Qt.darkGray)

        return radar_img, self.radar_info, True

    def _get_vpk_path(self, map_name, addon=None):
        """
        Get the VPK path for the specified map.

        Args:
            map_name: The name of the map
            addon: The workshop addon ID if it's a workshop map

        Returns:
            str: Path to the VPK file or None if not found
        """
        if addon:
            vpk_path = os.path.join(get_workshop_folder(addon), f"{addon}_dir.vpk")
            if not os.path.isfile(vpk_path):
                if self.parent:
                    QMessageBox.critical(
                        self.parent,
                        "Missing Workshop Map",
                        f"The map '{map_name}' from addon '{addon}' was not found.\n"
                        "Verify that Counter Strike 2 is installed and you are subscribed to the workshop submission."
                    )
                return None
        else:
            vpk_path = get_official_vpk_path()
            if not os.path.isfile(vpk_path):
                if self.parent:
                    QMessageBox.critical(
                        self.parent,
                        "Missing Official Map",
                        f"The official map VPK for '{map_name}' was not found.\n"
                        "Verify that Counter Strike 2 is installed."
                    )
                return None

        return vpk_path

    def _load_radar_config(self, map_name, addon=None):
        """
        Load the radar configuration for the specified map.

        Args:
            map_name: The name of the map
            addon: The workshop addon ID if it's a workshop map

        Returns:
            bool: True if loading was successful, False otherwise
        """
        vpk_path = self._get_vpk_path(map_name, addon)
        if not vpk_path:
            return False

        cfg_path = f"resource/overviews/{map_name}.txt"
        try:
            with vpk.open(vpk_path) as p:
                cfgfile = p.get_file(cfg_path)
                raw = cfgfile.read().decode('utf-8')
            with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8') as t:
                t.write(raw)
                tmp = t.name
            rconfig = vdf.load(open(tmp))
            self.radar_info = load_radar_info(rconfig)
            return True
        except Exception as e:
            if self.parent:
                QMessageBox.critical(
                    self.parent,
                    "Map Load Error",
                    f"Failed to load map overview config for '{map_name}'.\nError: {e}"
                )
            return False

    def _fetch_radar_path(self, vpk_path, map_name):
        """
        Find the radar image path within the VPK file.

        Args:
            vpk_path: Path to the VPK file
            map_name: The name of the map

        Returns:
            str: Path to the radar image within the VPK or None if not found
        """
        matches = []
        try:
            with vpk.open(vpk_path) as p:
                for file_path in p:
                    lower_path = file_path.lower()
                    if "overheadmaps" in lower_path and f"{map_name.lower()}_radar" in lower_path and lower_path.endswith(
                            ".vtex_c"):
                        matches.append(file_path)
        except Exception:
            return None

        if not matches:
            return None

        if len(matches) > 1 and self.parent:
            items = [os.path.basename(x) for x in matches]
            choice, ok = QInputDialog.getItem(
                self.parent, "Select Radar", "Multiple radar images found.", items, 0, False)
            if ok:
                for file_path in matches:
                    if os.path.basename(file_path) == choice:
                        return file_path.replace("\\", "/")

        return matches[0].replace("\\", "/") if matches else None

    def _load_radar_image(self, vpk_path, map_name):
        """
        Load the radar image from the VPK file.

        Args:
            vpk_path: Path to the VPK file
            map_name: The name of the map

        Returns:
            QImage: The loaded radar image or None if loading failed
        """
        radar_path = self._fetch_radar_path(vpk_path, map_name)

        if radar_path and os.path.isfile(vpk_path):
            extracted_path = fetch_file_from_vpk(
                vpk_path,
                radar_path,
                "vtex_",
                ["-d", "--vpk_filepath", radar_path]
            )
            return load_qimage_from_path(extracted_path)
        else:
            return load_qimage_from_path(radar_path) if radar_path else None

    def apply_radar_to_scene(self, radar_img, scene, base_item):
        """
        Apply the loaded radar image to the scene.

        Args:
            radar_img: The radar image to apply
            scene: The QGraphicsScene to apply the image to
            base_item: The QGraphicsPixmapItem to set the image on

        Returns:
            tuple: (img_width, img_height) The dimensions of the applied image
        """
        if not radar_img or radar_img.isNull():
            radar_img = QImage(512, 512, QImage.Format_RGB888)
            radar_img.fill(Qt.darkGray)

        img_w, img_h = radar_img.width(), radar_img.height()
        scale_val = self.radar_info.get("scale", 1)
        w_scaled = int(img_w * scale_val)
        h_scaled = int(img_h * scale_val)
        pos_x = self.radar_info.get("pos_x", 0)
        pos_y = self.radar_info.get("pos_y", 0)

        pixmap = QPixmap.fromImage(radar_img).scaled(
            w_scaled, h_scaled, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
        )
        base_item.setPixmap(pixmap)
        base_item.setOffset(pos_x, pos_y - h_scaled)

        # Set scene rect with margin
        margin = 200
        x_min = pos_x
        x_max = pos_x + w_scaled
        y_min = pos_y - h_scaled
        y_max = pos_y
        scene.setSceneRect(
            x_min - margin,
            y_min - margin,
            (x_max - x_min) + 2 * margin,
            (y_max - y_min) + 2 * margin
        )

        return img_w, img_h

class RadarImageSaver:
    """
    Handles saving radar view images from the DemoViewer application.
    Provides functionality to save the current radar view as a PNG image.
    """

    def __init__(self, parent=None):
        """
        Initialize the RadarImageSaver.

        Args:
            parent: The parent widget (typically HeatmapWindow)
        """
        self.parent = parent

    def save_radar_image(self, scene, map_name=None):
        """
        Save the current radar view as a PNG image.

        Args:
            scene: The QGraphicsScene containing the radar view
            map_name: The name of the current map (optional)

        Returns:
            bool: True if save was successful, False otherwise
        """
        # Create output directory
        d = os.path.dirname(os.path.abspath(__file__))
        out = os.path.join(d, "test")
        os.makedirs(out, exist_ok=True)

        # Set default filename based on map name
        m = map_name if map_name else "unknown"
        default = os.path.join(out, f"{m}_radar_output.png")

        # Get save location from user
        name, _ = QFileDialog.getSaveFileName(
            self.parent,
            "Save Radar Image",
            default,
            "PNG Images (*.png);;All Files (*)"
        )

        if not name:
            return False

        # Validate scene dimensions
        sr = scene.sceneRect()
        if sr.width() < 1 or sr.height() < 1:
            QMessageBox.warning(self.parent, "Save Error", "Invalid scene rect.")
            return False

        # Create image with same dimensions as scene
        img = QImage(int(sr.width()), int(sr.height()), QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)

        # Render scene to image
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        scene.render(p, QRectF(img.rect()), sr)
        p.end()

        # Save image
        if not img.save(name, "PNG"):
            QMessageBox.warning(self.parent, "Save Error", f"Couldn't save to {name}")
            return False

        return True
