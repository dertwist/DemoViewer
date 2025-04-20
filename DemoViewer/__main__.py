import sys
import os
from PySide6.QtWidgets import QApplication
import qdarktheme

# Import the HeatmapWindow from the same package using absolute imports
from DemoViewer.window import HeatmapWindow

def main():
    app = QApplication(sys.argv)
    w = HeatmapWindow()
    qdarktheme.setup_theme()
    app.setStyleSheet(qdarktheme.load_stylesheet())
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()