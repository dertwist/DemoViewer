
import os
import glob
from PySide6.QtWidgets import QFileDialog, QMessageBox, QProgressDialog, QTreeWidgetItem
from PySide6.QtCore import Qt

from .parser import DemHeaderParseThread, DemoFileParser, CACHE_FOLDER, demoDataCache

class DemoViewerActions:
    """
    Handles actions for the DemoViewer application such as opening files
    and clearing cache.
    """

    @staticmethod
    def clear_cache(parent):
        """
        Clear both disk and memory cache for demo files.
        Args:
            parent: The parent widget for displaying dialogs
        """
        try:
            # Remove all files in CACHE_FOLDER
            for f in glob.glob(os.path.join(CACHE_FOLDER, "*")):
                try:
                    os.remove(f)
                except Exception:
                    pass
            # Clear in-memory cache
            if hasattr(demoDataCache, "clear"):
                demoDataCache.clear()
            elif isinstance(demoDataCache, dict):
                demoDataCache.clear()
            QMessageBox.information(parent, "Cache Cleared", "Demo cache has been cleared.")
        except Exception as e:
            QMessageBox.warning(parent, "Cache Error", f"Failed to clear cache:\n{e}")

    @staticmethod
    def open_dem(parent, loaded, dem_tree, map_combo, add_map_cb, load_map_cb, update_all_cb):
        """
        Open and parse DEM files with a progress dialog.
        Args:
            parent: The parent widget for displaying dialogs
            loaded: The list to append loaded demo dicts to
            dem_tree: The QTreeWidget to add items to
            map_combo: The QComboBox for map selection
            add_map_cb: Callback to add a map to internal structures
            load_map_cb: Callback to load a map (mname, addon)
            update_all_cb: Callback to update/rebuild all (footsteps, heatmap, info, selectors)
        """
        paths, _ = QFileDialog.getOpenFileNames(
            parent, "Open DEM Files", "", "DEM Files (*.dem);;All Files (*)")
        if not paths:
            return
        prog = QProgressDialog("Parsing DEM files...", "Cancel", 0, len(paths), parent)
        prog.setWindowModality(Qt.WindowModal)
        thread = DemHeaderParseThread(paths)

        def on_parsed(f, hdr, err):
            if prog.wasCanceled():
                return
            name = os.path.basename(f)
            if err:
                QMessageBox.warning(parent, "Parse Error", f"Error in '{name}':\n{err}")
                return
            mname = hdr.get("map_name", "")
            addon = hdr.get("addons", "")
            if not mname:
                QMessageBox.warning(parent, "Invalid DEM", f"No map_name in '{name}'.")
                return
            if not loaded:
                # First demo loaded
                load_map_cb(mname, addon)
                add_map_cb(mname)
                map_combo.setCurrentText(mname)
            try:
                dp = DemoFileParser(f)
            except Exception as e:
                QMessageBox.warning(parent, "Parser Error", f"Could not parse '{name}':\n{e}")
                return
            loaded.append({
                "file": f,
                "map": mname,
                "addons": addon,
                "enabled": True,
                "parser": dp
            })
            dem_item = QTreeWidgetItem([name])
            dem_item.setFlags(dem_item.flags() | Qt.ItemIsUserCheckable)
            dem_item.setCheckState(0, Qt.Checked)
            dem_tree.addTopLevelItem(dem_item)
            add_map_cb(mname)

        def on_info(fn, i, t, s):
            lbl = f"Parsing {fn} ({i}/{t})"
            if s:
                lbl += f" [{s/1024:.1f} KB]"
            prog.setLabelText(lbl)
            prog.setValue(i)

        def on_finish():
            prog.setValue(len(paths))
            prog.close()
            update_all_cb()

        thread.file_parsed.connect(on_parsed)
        thread.current_info.connect(on_info)
        thread.finished.connect(on_finish)
        prog.canceled.connect(lambda: thread.terminate())
        thread.start()
        prog.exec()
        thread.wait()
