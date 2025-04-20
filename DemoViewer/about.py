import os
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QDialogButtonBox
from PySide6.QtGui import QPixmap, QIcon, QDesktopServices
from PySide6.QtCore import Qt, QUrl
from .__init__ import __version__

# You may want to update these constants as needed
AUTHOR = "Twist"
GITHUB_URL = "https://github.com/yourusername"
TWITTER_URL = "https://x.com/der_twist"
PACKAGE_VERSION = __version__

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About DemoViewer")
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "appicon.ico")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label = QLabel()
            icon_label.setPixmap(pixmap)
            icon_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(icon_label)

        # Program name and version
        name_label = QLabel(f"<b>DemoViewer</b> <br>Version: {PACKAGE_VERSION}")
        name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(name_label)

        # Author
        author_label = QLabel(f"Author: {AUTHOR}")
        author_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(author_label)

        # Links
        links_layout = QHBoxLayout()
        github_btn = QPushButton("GitHub")
        github_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        links_layout.addWidget(github_btn)

        twitter_btn = QPushButton("Twitter")
        twitter_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(TWITTER_URL)))
        links_layout.addWidget(twitter_btn)

        layout.addLayout(links_layout)

        # Close button
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)