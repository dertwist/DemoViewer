
import os
import sys
import time
import re
import tempfile
import pickle
import json
import subprocess
import numpy as np
import pandas as pd

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGraphicsScene, QLabel, QSpacerItem, QSizePolicy,
    QFileDialog, QMessageBox, QStatusBar, QSplitter, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QProgressDialog, QInputDialog,
    QPushButton, QGroupBox, QGraphicsPixmapItem, QComboBox, QSpinBox
)
from PySide6.QtGui import QIcon, QPixmap, QImage, QPainter, QAction
from PySide6.QtCore import Qt, QRectF, Signal, Slot, QTimer, QThread

from demoparser2 import DemoParser
from .common import *
import vpk
import vdf

from scipy.ndimage import gaussian_filter
from matplotlib import colormaps
import matplotlib.colors as colors

from .widgets import (
    ZoomableGraphicsView,
    LabeledSliderSpinBox,
    RadarInfoWidget
)

# --- Caching Setup ---
try:
    from PySide6.QtCore import QCache
    demoDataCache = QCache(2_000_000_000)  # ~2GB
except ImportError:
    demoDataCache = {}

CACHE_FOLDER = os.path.join(os.getcwd(), "dem_cache")
os.makedirs(CACHE_FOLDER, exist_ok=True)

SESSION_RADAR_CACHE = {}
SESSION_TEMP_FOLDER = tempfile.mkdtemp(prefix="demoviewer_radars_")

# --- Utility Functions ---

def normalize_team_name(team_name):
    """
    Normalize team names to consistent CT/T format.
    """
    if not team_name:
        return None
    team_str = str(team_name).upper()
    if team_str in ('CT', 'COUNTERTERRORIST', 'COUNTER-TERRORIST', '3'):
        return 'CT'
    if team_str in ('T', 'TERRORIST', 'TERRORISTS', '2'):
        return 'T'
    return None

def external_cache_path(demo_path):
    base = os.path.basename(demo_path)
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", base)
    return os.path.join(CACHE_FOLDER, f"demcache_{safe_name}.pkl")

def check_cache_folder_size(max_size_bytes=2 * 1024 * 1024 * 1024):
    """
    Ensure the cache folder does not exceed max_size_bytes.
    Removes oldest files if necessary.
    """
    total_size = 0
    files = []
    for root, _, fs in os.walk(CACHE_FOLDER):
        for f in fs:
            fp = os.path.join(root, f)
            sz = os.path.getsize(fp)
            total_size += sz
            files.append((fp, sz))
    if total_size > max_size_bytes:
        files_sorted = sorted(files, key=lambda x: os.path.getmtime(x[0]))
        for fp, sz in files_sorted:
            if total_size <= max_size_bytes:
                break
            try:
                os.remove(fp)
                total_size -= sz
            except Exception:
                pass

# --- Main Parser Class ---

class DemoFileParser:
    """
    Parses a CS2 demo file and extracts header, round info, player info, deaths, and footsteps.
    Stores most popular weapons and player deaths as DataFrames.
    """
    def __init__(self, path):
        self.file = os.path.abspath(path)
        self.header = {}
        self.footsteps = []
        self.rounds = []
        self.players = set()
        self.player_teams = {}
        self.player_deaths = None  # DataFrame: all player deaths (with X/Y)
        self.weapon_popularity = None  # DataFrame: weapon, count
        self._parse()

    def _load_from_cache(self, cache_file):
        try:
            with open(cache_file, "rb") as f:
                loaded_data = pickle.load(f)
            self.header = loaded_data["header"]
            self.footsteps = loaded_data["footsteps"]
            self.rounds = loaded_data.get("rounds", [])
            self.players = set(loaded_data.get("players", []))
            self.player_teams = loaded_data.get("player_teams", {})
            self.player_deaths = loaded_data.get("player_deaths", None)
            self.weapon_popularity = loaded_data.get("weapon_popularity", None)
            if not isinstance(demoDataCache, dict):
                demoDataCache.insert(self.file, loaded_data, cost=len(self.footsteps))
            else:
                demoDataCache[self.file] = loaded_data
            return True
        except Exception:
            return False

    def _load_from_memory_cache(self):
        if not isinstance(demoDataCache, dict):
            if demoDataCache.contains(self.file):
                cached = demoDataCache[self.file]
                self.header = cached["header"]
                self.footsteps = cached["footsteps"]
                self.rounds = cached.get("rounds", [])
                self.players = set(cached.get("players", []))
                self.player_teams = cached.get("player_teams", {})
                self.player_deaths = cached.get("player_deaths", None)
                self.weapon_popularity = cached.get("weapon_popularity", None)
                return True
        else:
            if self.file in demoDataCache:
                cached = demoDataCache[self.file]
                self.header = cached["header"]
                self.footsteps = cached["footsteps"]
                self.rounds = cached.get("rounds", [])
                self.players = set(cached.get("players", []))
                self.player_teams = cached.get("player_teams", {})
                self.player_deaths = cached.get("player_deaths", None)
                self.weapon_popularity = cached.get("weapon_popularity", None)
                return True
        return False

    def _parse(self):
        cache_file = external_cache_path(self.file)
        # Try disk cache
        if os.path.isfile(cache_file) and self._load_from_cache(cache_file):
            return
        # Try in-memory cache
        if self._load_from_memory_cache():
            return

        parser = DemoParser(self.file)
        # --- Header ---
        try:
            self.header = parser.parse_header()
        except Exception:
            self.header = {}

        # --- Player Deaths and Weapons ---
        weapons_df = parser.parse_event(
            "player_death",
            player=["X", "Y"],
            other=["tick", "user_name", "attacker_name", "weapon", "total_rounds_played"]
        )
        if weapons_df is not None and not weapons_df.empty:
            weapons_df = weapons_df.rename(columns={"X": "user_X", "Y": "user_Y"})
            self.weapons = weapons_df.copy()
            weapon_counts = weapons_df['weapon'].value_counts().reset_index()
            weapon_counts.columns = ['weapon', 'count']
            self.weapon_popularity = weapon_counts
        else:
            self.weapons = pd.DataFrame()
            self.weapon_popularity = pd.DataFrame(columns=['weapon', 'count'])

        # --- Player Deaths DataFrame ---
        event_df = parser.parse_event("player_death", player=["X", "Y"], other=["total_rounds_played"])
        self.player_deaths = pd.DataFrame(columns=['user_name', 'X', 'Y'])
        if event_df is not None and not event_df.empty:
            # Prefer 'user_X'/'user_Y', fallback to 'X'/'Y'
            if 'user_X' in event_df.columns and 'user_Y' in event_df.columns:
                deaths_df = event_df.rename(columns={'user_X': 'X', 'user_Y': 'Y'})
                self.player_deaths = deaths_df[['user_name', 'X', 'Y']].dropna(subset=['X', 'Y'])
            elif 'X' in event_df.columns and 'Y' in event_df.columns:
                self.player_deaths = event_df[['user_name', 'X', 'Y']].dropna(subset=['X', 'Y'])

        # --- Footsteps, Players, Teams ---
        try:
            ticks_df = parser.parse_ticks(["X", "Y", "player", "team", "team_name", "name", "is_alive"])
        except Exception:
            ticks_df = None

        self.footsteps = []
        if ticks_df is not None and not ticks_df.empty:
            idx_array = ticks_df.index.values
            x_array = ticks_df.get("X", pd.Series([None]*len(idx_array))).values
            y_array = ticks_df.get("Y", pd.Series([None]*len(idx_array))).values
            player_array = ticks_df.get("player", ticks_df.get("name", pd.Series([None]*len(idx_array)))).values
            team_array = ticks_df.get("team", ticks_df.get("team_name", pd.Series([None]*len(idx_array)))).values
            for ix, xx, yy, pname, tname in zip(idx_array, x_array, y_array, player_array, team_array):
                if xx is not None and yy is not None:
                    norm_team = normalize_team_name(tname)
                    self.footsteps.append((ix, xx, yy, pname, norm_team))
                    if pname:
                        self.players.add(pname)
                        if norm_team in ("CT", "T"):
                            self.player_teams[pname] = norm_team

        # --- Rounds and Winners ---
        self.rounds = []
        round_end_df = parser.parse_event(
            "round_end",
            other=["winner", "total_rounds_played"]
        )
        if round_end_df is not None and not round_end_df.empty:
            for _, row in round_end_df.iterrows():
                winner = row.get("winner", None)
                round_num = row.get("total_rounds_played", None)
                winner_norm = normalize_team_name(winner)
                if winner_norm in ("CT", "T") and round_num is not None:
                    self.rounds.append({
                        "winner": winner_norm,
                        "round_num": int(round_num)
                    })

        # --- Player-Team Assignments ---
        try:
            player_info = parser.parse_player_info()
            if player_info is not None and not player_info.empty:
                for _, row in player_info.iterrows():
                    name = row.get("name")
                    team_num = row.get("team_number")
                    if name and team_num:
                        team = "CT" if team_num == 3 else "T" if team_num == 2 else None
                        if team:
                            self.player_teams[name] = team
                            self.players.add(name)
        except Exception:
            pass

        # Fallback: infer teams from ticks if still missing
        if not self.player_teams and ticks_df is not None and not ticks_df.empty:
            for _, row in ticks_df.iterrows():
                pname = row.get("player") or row.get("name")
                tname = row.get("team") or row.get("team_name")
                norm_team = normalize_team_name(tname)
                if pname and norm_team in ("CT", "T"):
                    self.player_teams[pname] = norm_team
                    self.players.add(pname)

        # --- Store to cache ---
        stored_data = {
            "header": self.header,
            "footsteps": self.footsteps,
            "rounds": self.rounds,
            "players": list(self.players),
            "player_teams": self.player_teams,
            "player_deaths": self.player_deaths,
            "weapon_popularity": self.weapon_popularity
        }
        if not isinstance(demoDataCache, dict):
            demoDataCache.insert(self.file, stored_data, cost=len(self.footsteps))
        else:
            demoDataCache[self.file] = stored_data

        check_cache_folder_size()
        try:
            with open(cache_file, "wb") as f:
                pickle.dump(stored_data, f)
        except Exception:
            pass

# --- Threaded Header Parser ---

class DemHeaderParseThread(QThread):
    file_parsed = Signal(str, dict, str)
    current_info = Signal(str, int, int, int)
    finished = Signal()

    def __init__(self, files):
        super().__init__()
        self.files = files

    def run(self):
        total = len(self.files)
        for i, path in enumerate(self.files):
            name = os.path.basename(path)
            fsize = os.path.getsize(path) if os.path.exists(path) else 0
            self.current_info.emit(name, i + 1, total, fsize)
            err = ""
            hdr = {}
            try:
                dp = DemoFileParser(path)
                hdr = dp.header
            except Exception as e:
                err = str(e)
            self.file_parsed.emit(path, hdr, err)
            time.sleep(0.1)
        self.finished.emit()
