import os
import numpy as np
from PySide6.QtWidgets import (
    QMainWindow, QGraphicsScene, QGraphicsPixmapItem, QStatusBar, QTreeWidget, QComboBox, QCheckBox,
    QSpinBox, QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QPushButton, QSplitter, QSizePolicy, QSpacerItem
)
from PySide6.QtGui import QIcon, QPixmap, QImage, QPainter, QAction
from PySide6.QtCore import Qt, QTimer, Slot

from .parser import *
from .radar import *
from .heatmap import *
from .actions import DemoViewerActions
from .about import AboutDialog

class TransparentHeatmapItem(QGraphicsPixmapItem):
    def paint(self, painter, option, widget=None):
        painter.setCompositionMode(QPainter.CompositionMode_Screen)
        super().paint(painter, option, widget)

class HeatmapWindow(QMainWindow):
    """
    DemoViewer with advanced heatmap overlay, brightness/contrast, gamma,
    improved downsampling, and external caching plus QCache for large data.
    Now with robust map switching and session radar image cache.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DemoViewer")
        self.setGeometry(100, 100, 1600, 1000)
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "appicon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            print(f"Application icon not found at: {icon_path}")

        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)

        # Data references
        self.loaded = []
        self.footsteps = []
        self.deaths = []
        self.maps = []
        self.map_name = None
        self.cur_addon = None
        self.radar_info = {"pos_x": 0, "pos_y": 0, "scale": 1}
        self.ct_win_pct = None
        self.t_win_pct = None

        self.base_img = QImage(512, 512, QImage.Format_RGB888)
        self.base_img.fill(Qt.darkGray)
        self.img_w, self.img_h = self.base_img.width(), self.base_img.height()

        self.cur_sigma = 5.0
        self.cmap_gamma = 1 / 3.0
        self.cur_colormap = "jet"
        self.heatmap_brightness = 0.0
        self.heatmap_contrast = 1.0
        self.downsample_n = 1

        # Scene and view
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, self.img_w, self.img_h)
        self.view = ZoomableGraphicsView(self.scene, self)
        self.view.mouse_moved.connect(self.mouse_moved)

        self.base_item = QGraphicsPixmapItem()
        self.base_item.setZValue(0)
        self.scene.addItem(self.base_item)

        self.hm_item = TransparentHeatmapItem()
        self.hm_item.setZValue(1)
        self.scene.addItem(self.hm_item)

        self.init_menu()

        # DEM Tree
        self.dem_tree = QTreeWidget()
        self.dem_tree.setHeaderLabels(["Active DEM Files"])
        self.dem_tree.itemChanged.connect(self.on_dem_change)

        # Radar Info widget
        self.info_widget = RadarInfoWidget()

        # Controls
        self.map_combo = QComboBox()
        self.map_combo.currentTextChanged.connect(self.map_changed)
        self.chk_img = QCheckBox("Show Radar Image")
        self.chk_img.setChecked(True)
        self.chk_img.toggled.connect(lambda state: self.base_item.setVisible(state))
        self.chk_hm = QCheckBox("Show Heatmap")
        self.chk_hm.setChecked(True)
        self.chk_hm.toggled.connect(self.hm_item.setVisible)

        self.max_res_spin = QSpinBox()
        self.max_res_spin.setRange(64, 1024)
        self.max_res_spin.setValue(512)

        self.downsample_widget = LabeledSliderSpinBox(
            "Downsample footsteps (N):", default_value=self.downsample_n,
            minimum=1, maximum=100, single_step=1, is_float=False
        )
        self.downsample_widget.valueChanged.connect(self.on_downsample_n_changed)

        self.sigma_widget = LabeledSliderSpinBox(
            "Sigma:", default_value=self.cur_sigma, minimum=0.0, maximum=50.0,
            single_step=0.1, is_float=True
        )
        self.sigma_widget.valueChanged.connect(self.on_sigma_changed)

        self.cmap_combo = QComboBox()
        self.cmap_combo.addItems(["hot", "jet", "viridis", "plasma", "inferno", "magma", "cividis"])
        self.cmap_combo.setCurrentText(self.cur_colormap)
        self.cmap_combo.currentTextChanged.connect(self.on_cmap_changed)

        self.brightness_widget = LabeledSliderSpinBox(
            "Brightness:", default_value=self.heatmap_brightness,
            minimum=-1.0, maximum=1.0, single_step=0.01, is_float=True
        )
        self.brightness_widget.valueChanged.connect(self.on_brightness_changed)

        self.contrast_widget = LabeledSliderSpinBox(
            "Contrast:", default_value=self.heatmap_contrast,
            minimum=0.0, maximum=2.0, single_step=0.01, is_float=True
        )
        self.contrast_widget.valueChanged.connect(self.on_contrast_changed)

        self.team_selector = QComboBox()
        self.team_selector.addItem("All")
        self.team_selector.addItem("CT")
        self.team_selector.addItem("T")
        self.team_selector.currentTextChanged.connect(self.on_team_changed)
        self.selected_team = "All"

        self.player_selector = QComboBox()
        self.player_selector.addItem("All")
        self.player_selector.currentTextChanged.connect(self.on_player_changed)
        self.selected_player = "All"

        # Data type selector (footsteps, deaths)
        self.data_type_selector = QComboBox()
        self.data_type_selector.addItem("Footsteps")
        self.data_type_selector.addItem("Player Deaths")
        self.data_type_selector.setCurrentText("Footsteps")
        self.selected_data_type = "Footsteps"
        self.data_type_selector.currentTextChanged.connect(self.on_data_type_changed)

        # Build layout
        ctrl = QWidget()
        vlay = QVBoxLayout(ctrl)

        map_group = QGroupBox("Map Selection")
        map_group_layout = QHBoxLayout(map_group)
        map_group_layout.addWidget(QLabel("Map:"))
        map_group_layout.addWidget(self.map_combo)
        map_group.setLayout(map_group_layout)
        vlay.addWidget(map_group)

        # Selection group with team and player on a new line
        selection_group = QGroupBox("Selection")
        selection_vlayout = QVBoxLayout(selection_group)

        # First row: Show selector
        show_layout = QHBoxLayout()
        show_layout.addWidget(QLabel("Show:"))
        show_layout.addWidget(self.data_type_selector)

        # Second row: Team and Player selectors
        team_player_layout = QHBoxLayout()
        team_player_layout.addWidget(QLabel("Team:"))
        team_player_layout.addWidget(self.team_selector)
        team_player_layout.addWidget(QLabel("Player:"))
        team_player_layout.addWidget(self.player_selector)

        # Add both rows to the vertical layout
        selection_vlayout.addLayout(show_layout)
        selection_vlayout.addLayout(team_player_layout)

        selection_group.setLayout(selection_vlayout)
        vlay.addWidget(selection_group)

        layers_group = QGroupBox("Layers")
        lay_v = QVBoxLayout(layers_group)
        lay_v.addWidget(self.chk_img)
        lay_v.addWidget(self.chk_hm)
        vlay.addWidget(layers_group)

        perf_grp = QGroupBox("Performance Settings")
        perf_lay = QVBoxLayout(perf_grp)
        perf_lay2 = QHBoxLayout()
        perf_lay2.addWidget(QLabel("Max Heatmap Resolution:"))
        perf_lay2.addWidget(self.max_res_spin)
        perf_lay.addLayout(perf_lay2)
        perf_lay.addWidget(self.downsample_widget)
        perf_grp.setLayout(perf_lay)
        vlay.addWidget(perf_grp)

        hm_group = QGroupBox("Heatmap Settings")
        hm_layout = QVBoxLayout(hm_group)
        hm_layout.addWidget(self.sigma_widget)
        cmap_box = QWidget()
        cmap_lay = QHBoxLayout(cmap_box)
        cmap_lay.addWidget(QLabel("Colormap:"))
        cmap_lay.addWidget(self.cmap_combo)
        cmap_box.setLayout(cmap_lay)
        hm_layout.addWidget(cmap_box)

        bc_box = QGroupBox("Brightness/Contrast")
        bc_lay = QVBoxLayout(bc_box)
        bc_lay.addWidget(self.brightness_widget)
        bc_lay.addWidget(self.contrast_widget)
        hm_layout.addWidget(bc_box)

        hm_group.setLayout(hm_layout)
        vlay.addWidget(hm_group)

        vlay.addWidget(self.info_widget)

        btn_save = QPushButton("Save Radar View")
        btn_save.clicked.connect(self.save_view)
        vlay.addWidget(btn_save)
        btn_reset = QPushButton("Reset View")
        btn_reset.clicked.connect(self.reset_view)
        vlay.addWidget(btn_reset)
        vlay.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.dem_tree)
        splitter.addWidget(self.view)
        splitter.addWidget(ctrl)
        splitter.setSizes([250, 1000, 350])
        main_w = QWidget(self)
        main_layout = QVBoxLayout(main_w)
        main_layout.addWidget(splitter)
        self.setCentralWidget(main_w)

        self.reset_view()
        self.update_info()

    def on_data_type_changed(self, val: str):
        if val != self.selected_data_type:
            self.selected_data_type = val
            self.update_heatmap()

    def init_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu("File")
        act = QAction("Open DEM Files...", self)
        act.triggered.connect(self.open_dem)
        fm.addAction(act)

        clear_cache_act = QAction("Clear Cache", self)
        clear_cache_act.triggered.connect(self.clear_cache)
        fm.addAction(clear_cache_act)
        fm.addAction(QAction("Exit", self, triggered=self.close))

        help_menu = mb.addMenu("Help")
        about_act = QAction("About", self)
        about_act.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_act)

        about_qt_act = QAction("About Qt", self)
        about_qt_act.triggered.connect(QApplication.instance().aboutQt)
        help_menu.addAction(about_qt_act)
    def show_about_dialog(self):
        dlg = AboutDialog(self)
        dlg.exec()

    def clear_cache(self):
        DemoViewerActions.clear_cache(self)

    def open_dem(self):
        DemoViewerActions.open_dem(
            parent=self,
            loaded=self.loaded,
            dem_tree=self.dem_tree,
            map_combo=self.map_combo,
            add_map_cb=self.add_map,
            load_map_cb=self.load_map,
            update_all_cb=lambda: [
                self.rebuild_footsteps(),
                self.update_heatmap(),
                self.update_info(),
                self.update_player_team_selectors()
            ]
        )

    def add_map(self, m):
        if m and m not in self.maps:
            self.maps.append(m)
            self.map_combo.addItem(m)

    def on_dem_change(self, item, col):
        nm = item.text(0)
        for d in self.loaded:
            if os.path.basename(d["file"]) == nm:
                d["enabled"] = (item.checkState(0) == Qt.Checked)
                break
        self.rebuild_footsteps()
        self.update_heatmap()
        self.update_info()
        self.update_player_team_selectors()

    def apply_downsampling(self, footsteps):
        n = max(1, int(self.downsample_n))
        if n <= 1 or len(footsteps) <= 1:
            return footsteps
        idxs = np.linspace(0, len(footsteps) - 1, num=(len(footsteps) // n), dtype=int)
        return [footsteps[i] for i in idxs]

    def load_map(self, mname, addon=None):
        self.cur_addon = addon
        self.active_map = mname
        loader = RadarLoader(self)
        radar_img, self.radar_info, success = loader.load_map_radar(mname, addon)
        if not success:
            return
        self.base_img = radar_img
        self.img_w, self.img_h = loader.apply_radar_to_scene(
            radar_img, self.scene, self.base_item
        )
        self.update_info()
        self.update_player_team_selectors()

    def update_heatmap(self):
        # Choose data source
        if self.selected_data_type == "Footsteps":
            source_items = self.footsteps
        elif self.selected_data_type == "Player Deaths":
            source_items = self.deaths
        else:
            source_items = []

        # Fix: Properly check for empty DataFrame or list
        is_empty = False
        if isinstance(source_items, (list, tuple)):
            is_empty = not source_items
        elif hasattr(source_items, "empty"):
            is_empty = source_items.empty
        else:
            is_empty = not bool(source_items)

        if is_empty:
            self.hm_item.setPixmap(QPixmap())
            return

        scale_val = self.radar_info.get("scale", 1)
        w_scaled = int(self.img_w * scale_val)
        h_scaled = int(self.img_h * scale_val)
        pos_x = self.radar_info.get("pos_x", 0)
        pos_y = self.radar_info.get("pos_y", 0)

        player_team_map = {}
        for d in self.loaded:
            if d["enabled"]:
                player_team_map.update(getattr(d["parser"], "player_teams", {}))

        filtered = []
        if self.selected_data_type == "Footsteps":
            for (idx, x, y, pname, tname) in source_items:
                if self.selected_team != "All" and tname != self.selected_team:
                    continue
                if self.selected_player != "All" and pname != self.selected_player:
                    continue
                if x is None or y is None:
                    continue
                lx = (x - pos_x)
                ly = (y - (pos_y - h_scaled))
                filtered.append((idx, lx, ly))
        elif self.selected_data_type == "Player Deaths":
            for _, row in source_items.iterrows():
                # Use project format: X, Y, user_name
                x, y = row.get("X"), row.get("Y")
                pname = row.get("user_name")
                tname = player_team_map.get(pname)
                if self.selected_team != "All" and tname != self.selected_team:
                    continue
                if self.selected_player != "All" and pname != self.selected_player:
                    continue
                if x is None or y is None:
                    continue
                lx = (x - pos_x)
                ly = (y - (pos_y - h_scaled))
                filtered.append((row.get("tick", 0), lx, ly))

        if not filtered:
            self.hm_item.setPixmap(QPixmap())
            return

        max_dim = self.max_res_spin.value()
        downsample = 1
        if w_scaled > max_dim or h_scaled > max_dim:
            downsample = max(w_scaled / max_dim, h_scaled / max_dim)

        w_final = max(1, int(w_scaled / downsample))
        h_final = max(1, int(h_scaled / downsample))

        ds_items = [(idx, lx / downsample, ly / downsample) for idx, lx, ly in filtered]

        from scipy.ndimage import gaussian_filter
        raw_heat = calc_heatmap_np(ds_items, w_final, h_final)
        if self.cur_sigma > 0:
            raw_heat = gaussian_filter(raw_heat, self.cur_sigma)

        hm_qimg = heatmap_to_qimage(
            raw_heat,
            cmap=self.cur_colormap,
            gamma=self.cmap_gamma,
            brightness=self.heatmap_brightness,
            contrast=self.heatmap_contrast
        )
        if hm_qimg.isNull():
            self.hm_item.setPixmap(QPixmap())
            return

        if downsample > 1:
            pm = QPixmap.fromImage(
                hm_qimg.scaled(w_scaled, h_scaled, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            )
        else:
            pm = QPixmap.fromImage(hm_qimg)

        self.hm_item.setPixmap(pm)
        self.hm_item.setOffset(pos_x, pos_y - h_scaled)

    @Slot()
    def reset_view(self):
        self.view.resetTransform()
        r = self.scene.sceneRect()
        if r.width() > 0 and r.height() > 0:
            self.view.fitInView(r, Qt.KeepAspectRatio)
            QTimer.singleShot(50, lambda: self.view.fitInView(r, Qt.KeepAspectRatio))

    def map_changed(self, nm):
        if not self.loaded or not nm:
            return
        addon = None
        for d in self.loaded:
            if d["map"] == nm:
                addon = d["addons"]
                break
        if nm == self.map_name and addon == self.cur_addon:
            idx = self.map_combo.findText(nm)
            if idx != -1 and self.map_combo.currentIndex() != idx:
                self.map_combo.blockSignals(True)
                self.map_combo.setCurrentIndex(idx)
                self.map_combo.blockSignals(False)
            self.update_info()
            self.update_heatmap()
            self.update_player_team_selectors()
            return
        view_transform = self.view.transform()
        self.map_name = nm
        self.cur_addon = addon
        idx = self.map_combo.findText(nm)
        if idx != -1 and self.map_combo.currentIndex() != idx:
            self.map_combo.blockSignals(True)
            self.map_combo.setCurrentIndex(idx)
            self.map_combo.blockSignals(False)
        self.footsteps = []
        self.hm_item.setPixmap(QPixmap())
        self.base_item.setPixmap(QPixmap())
        self.load_map(nm, addon)
        self.rebuild_footsteps()
        self.update_heatmap()
        self.update_info()
        self.update_player_team_selectors()
        self.view.setTransform(view_transform)

    def mouse_moved(self, sx, sy):
        s = self.radar_info.get("scale", 1)
        px = self.radar_info.get("pos_x", 0)
        py = self.radar_info.get("pos_y", 0)
        wx = sx * s + px
        wy = sy * s + py
        self.statusBar.showMessage(f"Scene: ({sx:.2f}, {sy:.2f}) | World: ({wx:.2f}, {wy:.2f})")

    def update_info(self):
        addon = self.cur_addon if self.cur_addon else "N/A"
        map_name = self.map_name if self.map_name else "N/A"
        pts = len(self.footsteps)
        ct_wins, t_wins, total = 0, 0, 0
        for d in self.loaded:
            if d["enabled"] and hasattr(d["parser"], "rounds"):
                for rnd in getattr(d["parser"], "rounds", []):
                    winner = rnd.get("winner")
                    if winner == "CT":
                        ct_wins += 1
                    elif winner == "T":
                        t_wins += 1
        total = ct_wins + t_wins
        ct_pct = (ct_wins / total * 100) if total > 0 else 0
        t_pct = (t_wins / total * 100) if total > 0 else 0
        self.ct_win_pct = ct_pct
        self.t_win_pct = t_pct
        self.info_widget.update_info(addon, map_name, pts, ct_pct, t_pct)

    def update_player_team_selectors(self):
        players = set()
        teams = set(["CT", "T"])
        player_teams = {}
        for d in self.loaded:
            if not d["enabled"] or not hasattr(d["parser"], "players"):
                continue
            demo_players = getattr(d["parser"], "players", set())
            if demo_players:
                players.update(demo_players)
            demo_teams = getattr(d["parser"], "player_teams", {})
            if demo_teams:
                player_teams.update(demo_teams)
                teams.update(set(t for t in demo_teams.values() if t in ("CT", "T")))
        current_team = self.team_selector.currentText()
        self.team_selector.blockSignals(True)
        self.team_selector.clear()
        self.team_selector.addItem("All")
        for t in sorted(teams):
            self.team_selector.addItem(t)
        idx = self.team_selector.findText(current_team)
        if idx != -1:
            self.team_selector.setCurrentIndex(idx)
        else:
            self.team_selector.setCurrentIndex(0)
        self.team_selector.blockSignals(False)
        current_player = self.player_selector.currentText()
        self.player_selector.blockSignals(True)
        self.player_selector.clear()
        self.player_selector.addItem("All")
        for p in sorted(players):
            if p:
                self.player_selector.addItem(p)
        idx = self.player_selector.findText(current_player)
        if idx != -1:
            self.player_selector.setCurrentIndex(idx)
        else:
            self.player_selector.setCurrentIndex(0)
        self.player_selector.blockSignals(False)
        self.selected_team = self.team_selector.currentText()
        self.selected_player = self.player_selector.currentText()

    def on_team_changed(self, val):
        if val != self.selected_team:
            self.selected_team = val
            self.update_heatmap()

    def on_player_changed(self, val):
        if val != self.selected_player:
            self.selected_player = val
            self.update_heatmap()

    def rebuild_footsteps(self):
        self.footsteps = []
        self.deaths = []
        for d in self.loaded:
            if not d["enabled"]:
                continue
            parser = d.get("parser")
            if not parser:
                continue
            self.footsteps.extend(getattr(parser, "footsteps", []))
            deaths_df = getattr(parser, "player_deaths", None)
            if deaths_df is not None and not deaths_df.empty:
                self.deaths.append(deaths_df)
        # Concatenate all deaths DataFrames into one
        if self.deaths:
            import pandas as pd
            self.deaths = pd.concat(self.deaths, ignore_index=True)
        else:
            self.deaths = None
        self.footsteps = self.apply_downsampling(self.footsteps)

    def on_sigma_changed(self, val):
        self.cur_sigma = val
        self.update_heatmap()

    def on_brightness_changed(self, val):
        self.heatmap_brightness = val
        self.update_heatmap()

    def on_contrast_changed(self, val):
        self.heatmap_contrast = val
        self.update_heatmap()

    def on_cmap_changed(self, text):
        self.cur_colormap = text
        self.update_heatmap()

    def on_downsample_n_changed(self, val):
        self.downsample_n = int(val)
        self.rebuild_footsteps()
        self.update_heatmap()
        self.update_info()
        self.update_player_team_selectors()

    def save_view(self):
        saver = RadarImageSaver(self)
        saver.save_radar_image(self.scene, self.map_name)
