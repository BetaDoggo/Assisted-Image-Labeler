import sys
import os
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLabel, QFileDialog, QSplitter, QLineEdit, QStyle, QStyleFactory, QScrollArea
from PyQt5.QtGui import QPixmap, QIcon, QPalette, QColor, QResizeEvent
from PyQt5.QtCore import Qt, QSize

class ScalableImageLabel(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setText("No image loaded")
        self.pixmap = None

    def setPixmap(self, pixmap):
        self.pixmap = pixmap
        self.updatePixmap()

    def updatePixmap(self):
        if self.pixmap:
            scaled_pixmap = self.pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            super().setPixmap(scaled_pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updatePixmap()

class ImageTextPairApp(QWidget):
    def __init__(self):
        super().__init__()
        self.current_image_index = -1
        self.image_files = []
        self.current_directory = ""
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Image Labeler')
        self.setGeometry(100, 100, 1200, 800)

        # Main layout
        main_layout = QVBoxLayout()

        # Create a splitter for image and text
        splitter = QSplitter(Qt.Vertical)

        # Image navigation layout
        image_widget = QWidget()
        image_layout = QVBoxLayout(image_widget)
        nav_layout = QHBoxLayout()
        
        self.prev_button = QPushButton('', self)
        self.prev_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowLeft))
        self.prev_button.clicked.connect(self.previous_image)
        
        self.next_button = QPushButton('', self)
        self.next_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowRight))
        self.next_button.clicked.connect(self.next_image)

        # Image display
        self.scroll_area = QScrollArea()
        self.image_label = ScalableImageLabel()
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setWidgetResizable(True)

        nav_layout.addWidget(self.prev_button)
        nav_layout.addStretch(1)
        nav_layout.addWidget(self.next_button)

        image_layout.addWidget(self.scroll_area)
        image_layout.addLayout(nav_layout)

        # Text input
        text_widget = QWidget()
        text_layout = QVBoxLayout(text_widget)
        self.text_edit = QTextEdit(self)
        self.text_edit.setPlaceholderText("Enter image description here...")
        text_layout.addWidget(self.text_edit)

        # Add image and text widgets to splitter
        splitter.addWidget(image_widget)
        splitter.addWidget(text_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        # Buttons
        button_layout = QHBoxLayout()
        load_button = QPushButton('Load Directory', self)
        load_button.clicked.connect(self.load_directory)
        save_button = QPushButton('Save Description', self)
        save_button.clicked.connect(self.save_description)
        next_unlabeled_button = QPushButton('Next Unlabeled', self)
        next_unlabeled_button.clicked.connect(self.next_unlabeled_image)
        button_layout.addWidget(load_button)
        button_layout.addWidget(save_button)
        button_layout.addWidget(next_unlabeled_button)

        # Jump to image layout
        jump_layout = QHBoxLayout()
        self.jump_input = QLineEdit(self)
        self.jump_input.setPlaceholderText("Enter image number")
        jump_button = QPushButton('Jump to Image', self)
        jump_button.clicked.connect(self.jump_to_image)
        jump_layout.addWidget(self.jump_input)
        jump_layout.addWidget(jump_button)

        # Add widgets to main layout
        main_layout.addWidget(splitter)
        main_layout.addLayout(button_layout)
        main_layout.addLayout(jump_layout)

        self.setLayout(main_layout)

    def load_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if dir_path:
            self.current_directory = dir_path
            self.image_files = [f for f in os.listdir(dir_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))]
            if self.image_files:
                self.current_image_index = 0
                self.load_current_image()
            else:
                self.image_label.setText("No images found in the selected directory")

    def load_current_image(self):
        if 0 <= self.current_image_index < len(self.image_files):
            file_name = os.path.join(self.current_directory, self.image_files[self.current_image_index])
            pixmap = QPixmap(file_name)
            self.image_label.setPixmap(pixmap)
            self.load_description()

    def previous_image(self):
        if self.current_image_index > 0:
            self.save_description()
            self.current_image_index -= 1
            self.load_current_image()

    def next_image(self):
        if self.current_image_index < len(self.image_files) - 1:
            self.save_description()
            self.current_image_index += 1
            self.load_current_image()

    def next_unlabeled_image(self):
        self.save_description()
        for i in range(self.current_image_index + 1, len(self.image_files)):
            txt_path = os.path.splitext(os.path.join(self.current_directory, self.image_files[i]))[0] + '.txt'
            if not os.path.exists(txt_path) or os.path.getsize(txt_path) == 0:
                self.current_image_index = i
                self.load_current_image()
                return
        print("No more unlabeled images found")

    def jump_to_image(self):
        try:
            new_index = int(self.jump_input.text()) - 1
            if 0 <= new_index < len(self.image_files):
                self.save_description()
                self.current_image_index = new_index
                self.load_current_image()
            else:
                print("Invalid image number")
        except ValueError:
            print("Please enter a valid number")

    def load_description(self):
        current_image = os.path.join(self.current_directory, self.image_files[self.current_image_index])
        txt_path = os.path.splitext(current_image)[0] + '.txt'
        try:
            with open(txt_path, 'r') as f:
                self.text_edit.setText(f.read())
        except FileNotFoundError:
            self.text_edit.clear()

    def save_description(self):
        if self.image_files:
            current_image = os.path.join(self.current_directory, self.image_files[self.current_image_index])
            txt_path = os.path.splitext(current_image)[0] + '.txt'
            with open(txt_path, 'w') as f:
                f.write(self.text_edit.toPlainText())

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.image_label.updatePixmap()

def set_dark_theme(app):
    app.setStyle(QStyleFactory.create("Fusion"))
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(palette)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    set_dark_theme(app)
    ex = ImageTextPairApp()
    ex.show()
    sys.exit(app.exec_())