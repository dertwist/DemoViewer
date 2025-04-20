import winreg, os, re, vdf, subprocess, tempfile, vpk
import sys

from PySide6.QtGui import QImage
def get_steam_install_path():
    """
    Retrieve the Steam installation path from the Windows Registry.
    """
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam") as key:
            steam_path, _ = winreg.QueryValueEx(key, "InstallPath")
            return steam_path
    except WindowsError:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam") as key:
                steam_path, _ = winreg.QueryValueEx(key, "InstallPath")
                return steam_path
        except WindowsError as e:
            print(f"Error reading Steam install path: {e}")
            return None


def get_steam_library_folders(steam_path):
    """
    Retrieve all Steam library folders from the libraryfolders.vdf file.
    """
    library_folders = [steam_path]
    vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")

    try:
        with open(vdf_path, "r") as f:
            content = f.read()
            matches = re.findall(r'"path"\s+"([^"]+)"', content)
            library_folders.extend(matches)
    except Exception as e:
        print(f"Error reading libraryfolders.vdf: {e}")

    return library_folders


def find_counter_strike_path(library_folders):
    """
    Look for the Counter-Strike installation directory within the given library folders.
    """
    csgo_path_suffix = os.path.join("steamapps", "common", "Counter-Strike Global Offensive")
    for folder in library_folders:
        csgo_path = os.path.join(folder, csgo_path_suffix)
        if os.path.exists(csgo_path):
            return csgo_path
    return None


def get_counter_strike_path_from_registry():
    """
    Main function to get the Counter-Strike installation path.
    """
    steam_path = get_steam_install_path()
    if not steam_path:
        return None

    library_folders = get_steam_library_folders(steam_path)
    csgo_path = find_counter_strike_path(library_folders)
    return csgo_path

def get_decompiler_path():
    path = os.path.join(os.path.dirname(__file__), 'external','Decompiler.exe')
    print(path)
    return path
    # return r"external\Decompiler.exe"
    # return r"D:\CG\Projects\Other\Cs2DemoParser\DemoViewer\external\Decompiler.exe"



def fetch_file_from_vpk(vpk_path, internal_path, temp_prefix="file_decompiled_", extra_args=None, timeout=30000):
    """
    Attempt to extract a file from a VPK archive. If found, run an external external tool.
    Return the final path to the extracted output.
    """
    if extra_args is None:
        extra_args = []
    file_data = None
    try:
        with vpk.open(vpk_path) as pak:
            for fp in pak:
                if fp.lower() == internal_path.lower():
                    file_data = pak.get_file(fp).read()
                    break
    except:
        return None

    if not file_data:
        return None

    if not os.path.isfile(get_decompiler_path()):
        return None

    temp_folder = tempfile.mkdtemp(prefix=temp_prefix)
    cmd = [get_decompiler_path(), "-i", vpk_path, "--output", temp_folder] + extra_args
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout / 1000)
        if result.returncode != 0:
            return None
    except:
        return None

    outputs = []
    for root, _, files in os.walk(temp_folder):
        for f in files:
            outputs.append(os.path.join(root, f))
    if not outputs:
        return None
    if len(outputs) == 1:
        return outputs[0]
    # Try known extensions first
    for ext in [".png", ".jpg", ".txt"]:
        for outf in outputs:
            if outf.lower().endswith(ext):
                return outf
    # Otherwise return the first file
    return outputs[0]


def get_official_vpk_path():
    """Try reading the official Steam path for pak01_dir.vpk."""
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
        install_path, _ = winreg.QueryValueEx(key, "InstallPath")
        winreg.CloseKey(key)
        path_candidate = os.path.join(
            install_path, "steamapps", "common",
            "Counter-Strike Global Offensive", "game", "csgo", "pak01_dir.vpk"
        )
        if os.path.exists(path_candidate):
            return path_candidate
    except:
        pass
    return "E:\\SteamLibrary\\steamapps\\common\\Counter-Strike Global Offensive\\game\\csgo\\pak01_dir.vpk"


def get_counter_strike_path():
    return get_counter_strike_path_from_registry()


def get_workshop_folder(addon_id=None):
    """
    Attempt to build the path to the workshop folder.
    If addon_id is specified, append it. Otherwise return base folder.
    """
    csgo_path = get_counter_strike_path()
    if not csgo_path:
        raise ValueError("Cannot find CS:GO path.")
    steam_library = os.path.dirname(os.path.dirname(os.path.dirname(csgo_path)))
    base = os.path.join(steam_library, "steamapps", "workshop", "content", "730")
    return os.path.join(base, addon_id) if addon_id else base


def load_qimage_from_path(path_):
    """Return a QImage if valid, otherwise None."""
    if path_ and os.path.isfile(path_):
        img = QImage(path_)
        if not img.isNull():
            return img
    return None


def load_radar_info(data):
    """
    Parse VDF config for the radar info. Return a dict with pos_x, pos_y, scale.
    """
    if data and isinstance(data, dict):
        map_key = list(data.keys())[0]
        m_info = data[map_key]
        px = float(m_info.get("pos_x", 0))
        py = float(m_info.get("pos_y", 0))
        sc = float(m_info.get("scale", 1)) or 1.0
        print({"pos_x": px, "pos_y": py, "scale": sc})
        return {"pos_x": px, "pos_y": py, "scale": sc}
