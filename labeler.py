import os
import sys
from PIL import Image
from wd_tagger.tagger import ImageTagger
import fal_client
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLabel, QFileDialog, 
                             QSplitter, QLineEdit, QStyle, QStyleFactory, QScrollArea, QDialog, QCheckBox, QFormLayout, QMessageBox,
                             QFrame, QComboBox, QStackedWidget, QSpinBox, QSlider)
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

        self.api_key_input = QLineEdit()
        self.api_key_input.setText(self.settings.value("fal_api_key", ""))
        self.api_key_input.setEchoMode(QLineEdit.Password)
        layout.addRow("Fal API Key:", self.api_key_input)

        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_settings)
        layout.addRow(save_button)

    def save_settings(self):
        self.settings.setValue("autosave", self.autosave_checkbox.isChecked())
        self.settings.setValue("fal_api_key", self.api_key_input.text())
        self.accept()

class ImageTextPairApp(QWidget):
    def __init__(self):
        super().__init__()
        self.current_image_index = -1
        self.image_files = []
        self.current_directory = ""
        self.settings = QSettings("GoodCompany", "Labeler")
        self.initUI()
    
    def toggle_model_options(self, model):
        llava_models = ["LLavaV15_13B", "LLavaV16_34B"]
        show = model in llava_models

        self.prompt_label.setVisible(show)
        self.prompt_input.setVisible(show)
        self.max_tokens_label.setVisible(show)
        self.max_tokens_input.setVisible(show)
        self.temp_label.setVisible(show)
        self.temp_slider.setVisible(show)
        self.temp_value.setVisible(show)
        self.top_p_label.setVisible(show)
        self.top_p_slider.setVisible(show)
        self.top_p_value.setVisible(show)

    def reset_generation_status(self):
        if hasattr(self, 'generation_status'):
            self.generation_status.setText("Status: Ready")

    def on_provider_changed(self, provider):
            if provider == "Fal":
                self.stacked_widget.setCurrentIndex(0)
            else:  # Local
                self.stacked_widget.setCurrentIndex(1)

    def update_temp_value(self):
        self.temp_value.setText(f"{self.temp_slider.value() / 10:.1f}")

    def update_top_p_value(self):
        self.top_p_value.setText(f"{self.top_p_slider.value() / 10:.1f}")

    def update_general_threshold_label(self):
        value = self.general_threshold_slider.value() / 100
        self.general_threshold_label.setText(f"General Threshold: {value:.2f}")

    def update_character_threshold_label(self):
        value = self.character_threshold_slider.value() / 100
        self.character_threshold_label.setText(f"Character Threshold: {value:.2f}")

    def generate_wd_caption(self):
        if not self.image_files:
            QMessageBox.warning(self, "No Image", "Please load an image first.")
            return

        self.local_status_label.setText("Status: Generating...")
        self.local_generate_button.setEnabled(False)
        QApplication.processEvents()

        try:
            current_image = os.path.join(self.current_directory, self.image_files[self.current_image_index])
            model = self.local_model_dropdown.currentText().lower().replace("-", "")

            general_threshold = self.general_threshold_slider.value() / 100
            character_threshold = self.character_threshold_slider.value() / 100

            wdtagger = ImageTagger()
            result = wdtagger.tag_image(
                current_image,
                model=model,
                general=self.include_general.isChecked(),
                rating=self.include_rating.isChecked(),
                character=self.include_character.isChecked(),
                general_threshold=general_threshold,
                character_threshold=character_threshold,
                general_mcut=self.general_mcut.isChecked(),
                character_mcut=self.character_mcut.isChecked()
            )

            caption_mode = self.local_caption_mode_dropdown.currentText()
            if caption_mode == "Append":
                current_text = self.text_edit.toPlainText()
                if current_text:
                    self.text_edit.setText(f"{current_text}\n\n{result}")
                else:
                    self.text_edit.setText(result)
            else:  # Replace
                self.text_edit.setText(result)

            self.local_status_label.setText("Status: Generation Complete")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
            self.local_status_label.setText("Status: Generation Failed")
        finally:
            self.local_generate_button.setEnabled(True)

    def generate_fal_caption(self):
        if not self.image_files:
            QMessageBox.warning(self, "No Image", "Please load an image first.")
            return

        current_image = os.path.join(self.current_directory, self.image_files[self.current_image_index])
        prompt = self.prompt_input.toPlainText()
        max_tokens = self.max_tokens_input.value()
        temp = self.temp_slider.value() / 10
        top_p = self.top_p_slider.value() / 10
        model = self.models_dropdown.currentText()
        api_key = self.settings.value("fal_api_key", "")
        caption_mode = self.caption_mode_dropdown.currentText()

        if not api_key:
            QMessageBox.warning(self, "Missing API Key", "Please set your Fal API key in the Settings.")
            return

        self.generation_status.setText("Status: Generating...")
        self.generate_button.setEnabled(False)
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        QApplication.processEvents()

        try:
            output_text = self.describe_image(current_image, prompt, max_tokens, temp, top_p, model, api_key)

            if caption_mode == "Append":
                current_text = self.text_edit.toPlainText()
                if current_text:
                    self.text_edit.setText(f"{current_text}\n\n{output_text}")
                else:
                    self.text_edit.setText(output_text)
            else:  # Replace
                self.text_edit.setText(output_text)

            self.generation_status.setText("Status: Generation Complete")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
            self.generation_status.setText("Status: Generation Failed")
        finally:
            self.generate_button.setEnabled(True)
            self.prev_button.setEnabled(True)
            self.next_button.setEnabled(True)

    def describe_image(self, image_path, prompt, max_tokens, temp, top_p, model, api_key):
        # Set api key
        os.environ["FAL_KEY"] = api_key
        
        models = {
            "LLavaV15_13B": "fal-ai/llavav15-13b",
            "LLavaV16_34B": "fal-ai/llava-next",
            "Florence_2_Large": "fal-ai/florence-2-large/detailed-caption",
        }
        endpoint = models.get(model)

        # Upload image
        with open(image_path, 'rb') as img_file:
            file = img_file.read()
        image_url = fal_client.upload(file, "image/png")
        
        if endpoint == "fal-ai/florence-2-large/detailed-caption":
            handler = fal_client.submit(
            endpoint,
            arguments={
                "image_url": image_url,})
            result = handler.get()
            output_text = result['results']
        else:
            handler = fal_client.submit(
                endpoint,
                arguments={
                    "image_url": image_url,
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": temp,
                    "top_p": top_p,
                }
            )
            result = handler.get()
            output_text = result['output']
        return output_text

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
        delete_counter_layout.addWidget(self.labeled_counter, alignment=Qt.AlignCenter)
        delete_counter_layout.addStretch(1)
        delete_counter_layout.addWidget(self.image_counter, alignment=Qt.AlignRight)

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
        button_layout.addWidget(load_button)
        button_layout.addWidget(save_button)
        button_layout.addWidget(next_unlabeled_button)

        left_panel.addLayout(button_layout)

        # Jump to image and Show Models layout
        jump_models_layout = QHBoxLayout()
        settings_button = QPushButton('Settings', self)
        settings_button.clicked.connect(self.open_settings)
        self.jump_input = QLineEdit(self)
        self.jump_input.setPlaceholderText("Enter image number")
        jump_button = QPushButton('Jump to Image', self)
        jump_button.clicked.connect(self.jump_to_image)
        self.show_models_button = QPushButton('Show Models', self)
        self.show_models_button.setCheckable(True)
        self.show_models_button.clicked.connect(self.toggle_models_panel)
        jump_models_layout.addWidget(settings_button)
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

        # Provider dropdown
        provider_layout = QHBoxLayout()
        provider_label = QLabel("Provider:")
        self.provider_dropdown = QComboBox()
        self.provider_dropdown.addItems(["Fal", "Local"])
        self.provider_dropdown.currentTextChanged.connect(self.on_provider_changed)
        provider_layout.addWidget(provider_label)
        provider_layout.addWidget(self.provider_dropdown)
        right_layout.addLayout(provider_layout)

        # Stacked widget for Fal and Local options
        self.stacked_widget = QStackedWidget()

        # Fal layout
        fal_widget = QWidget()
        fal_layout = QVBoxLayout(fal_widget)

        models_label = QLabel("Models:")
        self.models_dropdown = QComboBox()
        self.models_dropdown.addItems(["LLavaV15_13B", "LLavaV16_34B", "Florence_2_Large"])
        fal_layout.addWidget(models_label)
        fal_layout.addWidget(self.models_dropdown)
        self.models_dropdown.currentTextChanged.connect(self.toggle_model_options)

        self.prompt_label = QLabel("Prompt:")
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Enter prompt here...")
        fal_layout.addWidget(self.prompt_label)
        fal_layout.addWidget(self.prompt_input)

        self.max_tokens_label = QLabel("Max Tokens:")
        self.max_tokens_input = QSpinBox()
        self.max_tokens_input.setRange(1, 2048)
        self.max_tokens_input.setValue(256)
        fal_layout.addWidget(self.max_tokens_label)
        fal_layout.addWidget(self.max_tokens_input)

        self.temp_label = QLabel("Temperature:")
        self.temp_slider = QSlider(Qt.Horizontal)
        self.temp_slider.setRange(1, 10)
        self.temp_slider.setValue(2)
        self.temp_value = QLabel("0.2")
        temp_layout = QHBoxLayout()
        temp_layout.addWidget(self.temp_slider)
        temp_layout.addWidget(self.temp_value)
        fal_layout.addWidget(self.temp_label)
        fal_layout.addLayout(temp_layout)
        self.temp_slider.valueChanged.connect(self.update_temp_value)

        self.top_p_label = QLabel("Top P:")
        self.top_p_slider = QSlider(Qt.Horizontal)
        self.top_p_slider.setRange(1, 10)
        self.top_p_slider.setValue(10)
        self.top_p_value = QLabel("1.0")
        top_p_layout = QHBoxLayout()
        top_p_layout.addWidget(self.top_p_slider)
        top_p_layout.addWidget(self.top_p_value)
        fal_layout.addWidget(self.top_p_label)
        fal_layout.addLayout(top_p_layout)
        self.top_p_slider.valueChanged.connect(self.update_top_p_value)
        self.toggle_model_options(self.models_dropdown.currentText())

        self.caption_mode_label = QLabel("Caption Mode:")
        self.caption_mode_dropdown = QComboBox()
        self.caption_mode_dropdown.addItems(["Replace", "Append"])
        caption_mode_layout = QHBoxLayout()
        caption_mode_layout.addWidget(self.caption_mode_label)
        caption_mode_layout.addWidget(self.caption_mode_dropdown)
        fal_layout.addLayout(caption_mode_layout)

        self.generation_status = QLabel("Status: Ready")
        fal_layout.addWidget(self.generation_status)

        self.generate_button = QPushButton("Generate Caption")
        self.generate_button.clicked.connect(self.generate_fal_caption)
        fal_layout.addWidget(self.generate_button)
        fal_layout.addStretch(1)  # Push everything to the top
        self.stacked_widget.addWidget(fal_widget)

        # Local layout
        Local_widget = QWidget()
        Local_layout = QVBoxLayout(Local_widget)
        Local_layout.setSpacing(5)

        type_layout = QHBoxLayout()
        type_label = QLabel("Type:")
        self.type_dropdown = QComboBox()
        self.type_dropdown.addItem("wd-tagger")
        type_layout.addWidget(type_label)
        type_layout.addWidget(self.type_dropdown)
        Local_layout.addLayout(type_layout)

        model_layout = QHBoxLayout()
        model_label = QLabel("Model:")
        self.local_model_dropdown = QComboBox()
        self.local_model_dropdown.addItems(["vit3", "vit3-Large", "swinv3", "convnextv3"])
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.local_model_dropdown)
        Local_layout.addLayout(model_layout)

        # Add checkboxes
        self.include_general = QCheckBox("Include general")
        self.include_character = QCheckBox("Include character")
        self.include_rating = QCheckBox("Include rating")
        self.include_general.setChecked(True)
        self.include_character.setChecked(True)
        self.include_rating.setChecked(True)
        Local_layout.addWidget(self.include_general)
        Local_layout.addWidget(self.include_character)
        Local_layout.addWidget(self.include_rating)

        # Add sliders for thresholds
        self.general_threshold_slider = QSlider(Qt.Horizontal)
        self.general_threshold_slider.setRange(0, 100)
        self.general_threshold_slider.setValue(35)
        self.general_threshold_label = QLabel("General Threshold: 0.35")
        self.general_threshold_slider.valueChanged.connect(self.update_general_threshold_label)
        Local_layout.addWidget(self.general_threshold_label)
        Local_layout.addWidget(self.general_threshold_slider)

        self.character_threshold_slider = QSlider(Qt.Horizontal)
        self.character_threshold_slider.setRange(0, 100)
        self.character_threshold_slider.setValue(85)
        self.character_threshold_label = QLabel("Character Threshold: 0.85")
        self.character_threshold_slider.valueChanged.connect(self.update_character_threshold_label)
        Local_layout.addWidget(self.character_threshold_label)
        Local_layout.addWidget(self.character_threshold_slider)

        # Add checkboxes for mcut options
        self.general_mcut = QCheckBox("General MCUT")
        self.character_mcut = QCheckBox("Character MCUT")
        Local_layout.addWidget(self.general_mcut)
        Local_layout.addWidget(self.character_mcut)

        # Add caption mode dropdown
        caption_mode_layout = QHBoxLayout()
        caption_mode_label = QLabel("Caption Mode:")
        self.local_caption_mode_dropdown = QComboBox()
        self.local_caption_mode_dropdown.addItems(["Replace", "Append"])
        caption_mode_layout.addWidget(caption_mode_label)
        caption_mode_layout.addWidget(self.local_caption_mode_dropdown)
        Local_layout.addLayout(caption_mode_layout)

        # Add status label
        self.local_status_label = QLabel("Status: Ready")
        Local_layout.addWidget(self.local_status_label)

        # Add generate button
        self.local_generate_button = QPushButton("Generate Caption")
        self.local_generate_button.clicked.connect(self.generate_wd_caption)
        Local_layout.addWidget(self.local_generate_button)

        Local_layout.addStretch(1)
        self.stacked_widget.addWidget(Local_widget)

        right_layout.addWidget(self.stacked_widget)
        right_layout.addStretch(1)  # Push everything to the top
    
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
            self.reset_generation_status()

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