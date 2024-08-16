import sys
import os
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLabel, QFileDialog, 
                             QSplitter, QLineEdit, QStyle, QStyleFactory, QScrollArea, QDialog, QCheckBox, QFormLayout, QMessageBox,
                             QFrame)
from PyQt5.QtGui import QPixmap, QIcon, QPalette, QColor, QResizeEvent
from PyQt5.QtCore import Qt, QSize, QSettings

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

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.settings = QSettings("GoodCompany", "Labeler")

        layout = QFormLayout(self)

        self.autosave_checkbox = QCheckBox()
        self.autosave_checkbox.setChecked(self.settings.value("autosave", True, type=bool))
        layout.addRow("Autosave on navigation:", self.autosave_checkbox)

        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_settings)
        layout.addRow(save_button)

    def save_settings(self):
        self.settings.setValue("autosave", self.autosave_checkbox.isChecked())
        self.accept()

class ImageTextPairApp(QWidget):
    def __init__(self):
        super().__init__()
        self.current_image_index = -1
        self.image_files = []
        self.current_directory = ""
        self.settings = QSettings("GoodCompany", "Labeler")
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Labeler')
        self.setGeometry(100, 100, 1200, 800)

        # Main layout
        main_layout = QHBoxLayout()  # Changed to QHBoxLayout

        # Left panel (image and text)
        left_panel = QVBoxLayout()

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

        # Delete button and counters
        delete_counter_layout = QHBoxLayout()
        self.delete_button = QPushButton('Delete', self)
        self.delete_button.setStyleSheet("background-color: red; min-width: 60px; min-height: 30px;")
        self.delete_button.clicked.connect(self.delete_current_image)
        self.labeled_counter = QLabel("0/0 labeled")
        self.image_counter = QLabel("0/0")
        delete_counter_layout.addWidget(self.delete_button)
        delete_counter_layout.addStretch(1)
        delete_counter_layout.addWidget(self.labeled_counter)
        delete_counter_layout.addWidget(self.image_counter)

        nav_layout.addWidget(self.prev_button)
        nav_layout.addStretch(1)
        nav_layout.addWidget(self.next_button)

        image_layout.addLayout(delete_counter_layout)
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

        left_panel.addWidget(splitter)

        # Buttons
        button_layout = QHBoxLayout()
        load_button = QPushButton('Load Directory', self)
        load_button.clicked.connect(self.load_directory)
        save_button = QPushButton('Save Description', self)
        save_button.clicked.connect(self.save_description)
        next_unlabeled_button = QPushButton('Next Unlabeled', self)
        next_unlabeled_button.clicked.connect(self.next_unlabeled_image)
        settings_button = QPushButton('Settings', self)
        settings_button.clicked.connect(self.open_settings)
        button_layout.addWidget(load_button)
        button_layout.addWidget(save_button)
        button_layout.addWidget(next_unlabeled_button)
        button_layout.addWidget(settings_button)

        left_panel.addLayout(button_layout)

        # Jump to image and Show Models layout
        jump_models_layout = QHBoxLayout()
        self.jump_input = QLineEdit(self)
        self.jump_input.setPlaceholderText("Enter image number")
        jump_button = QPushButton('Jump to Image', self)
        jump_button.clicked.connect(self.jump_to_image)
        self.show_models_button = QPushButton('Show Models', self)
        self.show_models_button.setCheckable(True)
        self.show_models_button.clicked.connect(self.toggle_models_panel)
        jump_models_layout.addWidget(self.jump_input)
        jump_models_layout.addWidget(jump_button)
        jump_models_layout.addWidget(self.show_models_button)

        left_panel.addLayout(jump_models_layout)

        # Add left panel to main layout
        main_layout.addLayout(left_panel, 7)  # Giving more space to the left panel

        # Right panel (AI models)
        self.right_panel = QFrame()
        self.right_panel.setFrameShape(QFrame.StyledPanel)
        right_layout = QVBoxLayout(self.right_panel)
        
        # Placeholder for AI models
        ai_placeholder = QTextEdit()
        ai_placeholder.setPlaceholderText("AI models will be integrated here in the future.")
        ai_placeholder.setReadOnly(True)
        right_layout.addWidget(ai_placeholder)

        self.right_panel.hide()  # Initially hidden
        main_layout.addWidget(self.right_panel, 3)  # Giving less space to the right panel

        self.setLayout(main_layout)

    def toggle_models_panel(self):
        if self.show_models_button.isChecked():
            self.right_panel.show()
            self.show_models_button.setText('Hide Models')
        else:
            self.right_panel.hide()
            self.show_models_button.setText('Show Models')

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec_()

    def should_autosave(self):
        return self.settings.value("autosave", True, type=bool)

    def load_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if dir_path:
            self.current_directory = dir_path
            self.image_files = [f for f in os.listdir(dir_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))]
            if self.image_files:
                self.current_image_index = 0
                self.load_current_image()
                self.update_counters()
            else:
                self.image_label.setText("No images found in the selected directory")

    def load_current_image(self):
        if 0 <= self.current_image_index < len(self.image_files):
            file_name = os.path.join(self.current_directory, self.image_files[self.current_image_index])
            pixmap = QPixmap(file_name)
            self.image_label.setPixmap(pixmap)
            self.load_description()
            self.update_counters()

    def previous_image(self):
        if self.current_image_index > 0:
            if self.should_autosave():
                self.save_description()
            self.current_image_index -= 1
            self.load_current_image()

    def next_image(self):
        if self.current_image_index < len(self.image_files) - 1:
            if self.should_autosave():
                self.save_description()
            self.current_image_index += 1
            self.load_current_image()

    def next_unlabeled_image(self):
        if self.should_autosave():
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
                if self.should_autosave():
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
                content = f.read().strip()
                self.text_edit.setText(content)
        except FileNotFoundError:
            self.text_edit.clear()

    def save_description(self):
        if self.image_files:
            current_image = os.path.join(self.current_directory, self.image_files[self.current_image_index])
            txt_path = os.path.splitext(current_image)[0] + '.txt'
            content = self.text_edit.toPlainText().strip()
            
            if content:
                with open(txt_path, 'w') as f:
                    f.write(content)
            else:
                if os.path.exists(txt_path):
                    os.remove(txt_path)
            
            self.update_counters()

    def delete_current_image(self):
        if not self.image_files:
            return

        current_image = os.path.join(self.current_directory, self.image_files[self.current_image_index])
        txt_path = os.path.splitext(current_image)[0] + '.txt'

        # Create 'deleted' subfolder if it doesn't exist
        deleted_folder = os.path.join(self.current_directory, "deleted")
        os.makedirs(deleted_folder, exist_ok=True)

        # Move image file to 'deleted' folder
        deleted_image_path = os.path.join(deleted_folder, self.image_files[self.current_image_index])
        os.rename(current_image, deleted_image_path)

        # Move associated text file if it exists
        if os.path.exists(txt_path):
            deleted_txt_path = os.path.join(deleted_folder, os.path.basename(txt_path))
            os.rename(txt_path, deleted_txt_path)

        # Remove from list and update index
        del self.image_files[self.current_image_index]
        if self.current_image_index >= len(self.image_files):
            self.current_image_index = max(0, len(self.image_files) - 1)

        if self.image_files:
            self.load_current_image()
        else:
            self.image_label.setText("No images left in the directory")
            self.text_edit.clear()
        
        self.update_counters()

    def update_counters(self):
        total_images = len(self.image_files)
        labeled_images = sum(1 for img in self.image_files 
                             if os.path.exists(os.path.splitext(os.path.join(self.current_directory, img))[0] + '.txt') 
                             and os.path.getsize(os.path.splitext(os.path.join(self.current_directory, img))[0] + '.txt') > 0)
        
        self.image_counter.setText(f"{self.current_image_index + 1}/{total_images}")
        self.labeled_counter.setText(f"{labeled_images}/{total_images} labeled")

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