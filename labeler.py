import os
import sys
import requests
from wd_tagger.tagger import ImageTagger
import fal_client
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLabel, QFileDialog, 
                             QSplitter, QLineEdit, QStyle, QStyleFactory, QScrollArea, QDialog, QCheckBox, QFormLayout, QMessageBox,
                             QFrame, QComboBox, QStackedWidget, QSpinBox, QSlider, QProgressBar)
from PyQt5.QtGui import QPixmap, QPalette, QColor, QResizeEvent
from PyQt5.QtCore import Qt, QSettings, QThread, pyqtSignal

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

        self.fal_api_key_input = QLineEdit()
        self.fal_api_key_input.setText(self.settings.value("fal_api_key", ""))
        self.fal_api_key_input.setEchoMode(QLineEdit.Password)
        layout.addRow("Fal API Key:", self.fal_api_key_input)

        self.openrouter_api_key_input = QLineEdit()
        self.openrouter_api_key_input.setText(self.settings.value("openrouter_api_key", ""))
        self.openrouter_api_key_input.setEchoMode(QLineEdit.Password)
        layout.addRow("OpenRouter API Key:", self.openrouter_api_key_input)

        self.theme_dropdown = QComboBox()
        self.theme_dropdown.addItems(["Dark", "Light", "Lime"])
        self.theme_dropdown.setCurrentText(self.settings.value("theme", "Dark"))
        layout.addRow("Theme:", self.theme_dropdown)

        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_settings)
        layout.addRow(save_button)

    def save_settings(self):
        self.settings.setValue("autosave", self.autosave_checkbox.isChecked())
        self.settings.setValue("fal_api_key", self.fal_api_key_input.text())
        self.settings.setValue("openrouter_api_key", self.openrouter_api_key_input.text())
        self.settings.setValue("theme", self.theme_dropdown.currentText())
        self.accept()

class BatchProcessingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Processing")
        self.setGeometry(100, 100, 500, 200)
        self.setModal(True)
        self.layout = QVBoxLayout(self)
        
        # Provider label
        self.provider_label = QLabel(f"Provider: {self.parent().provider_dropdown.currentText()}")
        self.layout.addWidget(self.provider_label)
        
        # Checkbox for skipping captioned images
        self.skip_captioned = QCheckBox("Skip images with existing captions")
        self.skip_captioned.stateChanged.connect(self.update_button_text)
        self.layout.addWidget(self.skip_captioned)
        
        # Progress bar and label
        self.progress_label = QLabel("Ready to start")
        self.progress_bar = QProgressBar(self)
        
        # Caption All / Cancel button
        self.action_button = QPushButton("Caption All Images")
        self.action_button.clicked.connect(self.toggle_processing)

        self.layout.addStretch(1) 
        self.layout.addWidget(self.progress_label)
        self.layout.addWidget(self.action_button)
        self.layout.addWidget(self.progress_bar)

        self.worker = None
        self.is_processing = False
        self.update_button_text()

    def update_button_text(self):
        if self.is_processing:
            self.action_button.setText("Cancel")
        else:
            total_images = len(self.parent().image_files)
            if self.skip_captioned.isChecked():
                uncaptioned_images = sum(1 for img in self.parent().image_files
                                         if not os.path.exists(os.path.splitext(os.path.join(self.parent().current_directory, img))[0] + '.txt'))
                self.action_button.setText(f"Caption {uncaptioned_images} Images")
            else:
                self.action_button.setText(f"Caption {total_images} Images")

    def toggle_processing(self):
        if self.is_processing:
            self.stop_processing()
        else:
            self.start_processing()

    def start_processing(self):
        self.is_processing = True
        self.update_button_text()
        self.worker = BatchProcessingWorker(self.parent(), self.skip_captioned.isChecked())
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.caption_generated.connect(self.parent().update_caption)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def stop_processing(self):
        if self.worker:
            self.worker.requestInterruption()
            self.worker.wait()
        self.on_finished()

    def update_progress(self, value, total):
        self.progress_bar.setValue(value)
        self.progress_bar.setMaximum(total)
        self.progress_label.setText(f"Processed {value} out of {total} images")

    def on_finished(self):
        self.is_processing = False
        self.update_button_text()
        self.progress_label.setText("Batch processing completed")

class BatchProcessingWorker(QThread):
    progress_updated = pyqtSignal(int, int)
    caption_generated = pyqtSignal(int, str)
    finished = pyqtSignal()

    def __init__(self, main_app, skip_captioned):
        super().__init__()
        self.main_app = main_app
        self.skip_captioned = skip_captioned

    def run(self):
        total_images = len(self.main_app.image_files)
        processed = 0
        for i, image_file in enumerate(self.main_app.image_files):
            if self.isInterruptionRequested():
                break
            
            current_image = os.path.join(self.main_app.current_directory, image_file)
            txt_path = os.path.splitext(current_image)[0] + '.txt'
            
            if self.skip_captioned and os.path.exists(txt_path):
                continue
            
            if self.main_app.provider_dropdown.currentText() == "Local":
                result = self.generate_local_caption(current_image)
            elif self.main_app.provider_dropdown.currentText() == "Fal":
                result = self.generate_fal_caption(current_image)
            else:  # OpenRouter
                result = self.generate_openrouter_caption(current_image)
            
            self.caption_generated.emit(i, result)
            processed += 1
            self.progress_updated.emit(processed, total_images)
        self.finished.emit()

    def generate_local_caption(self, image_path):
        model = self.main_app.local_model_dropdown.currentText().lower().replace("-", "")
        general_threshold = self.main_app.general_threshold_slider.value() / 100
        character_threshold = self.main_app.character_threshold_slider.value() / 100

        wdtagger = ImageTagger()
        result = wdtagger.tag_image(
            image_path,
            model=model,
            general=self.main_app.include_general.isChecked(),
            rating=self.main_app.include_rating.isChecked(),
            character=self.main_app.include_character.isChecked(),
            general_threshold=general_threshold,
            character_threshold=character_threshold,
            general_mcut=self.main_app.general_mcut.isChecked(),
            character_mcut=self.main_app.character_mcut.isChecked()
        )
        return result

    def generate_fal_caption(self, image_path):
        prompt = self.main_app.prompt_input.toPlainText()
        max_tokens = self.main_app.max_tokens_input.value()
        temp = self.main_app.temp_slider.value() / 10
        top_p = self.main_app.top_p_slider.value() / 10
        model = self.main_app.models_dropdown.currentText()
        api_key = self.main_app.settings.value("fal_api_key", "")

        return self.main_app.fal_describe_image(image_path, prompt, max_tokens, temp, top_p, model, api_key)

    def generate_openrouter_caption(self, image_path):
        prompt = self.main_app.openrouter_prompt_input.toPlainText()
        model = self.main_app.openrouter_models_dropdown.currentText()
        api_key = self.main_app.settings.value("openrouter_api_key", "")
        max_tokens = self.main_app.openrouter_max_tokens_input.value()
        temperature = self.main_app.openrouter_temp_slider.value() / 100
        repetition_penalty = self.main_app.openrouter_rep_penalty_slider.value() / 100

        if self.main_app.openrouter_include_caption_checkbox.isChecked():
            current_caption = ""
            txt_path = os.path.splitext(image_path)[0] + '.txt'
            if os.path.exists(txt_path):
                with open(txt_path, 'r') as f:
                    current_caption = f.read().strip()
            prompt = prompt.replace("{caption}", f'"{current_caption}"')

        return self.main_app.openrouter_describe_image(prompt, model, api_key, max_tokens, temperature, repetition_penalty)

class ImageTextPairApp(QWidget):
    def __init__(self):
        super().__init__()
        self.current_image_index = -1
        self.image_files = []
        self.current_directory = ""
        self.settings = QSettings("GoodCompany", "Labeler")
        self.initUI()
        self.apply_theme()
        self.setFocusPolicy(Qt.StrongFocus)
    
    def closeEvent(self, event):
        if self.should_autosave():
            self.save_description()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self.delete_current_image()
        else:
            super().keyPressEvent(event)

    def toggle_model_options(self, model):
        llava_and_moondream_models = ["LLavaV15_13B", "LLavaV16_34B", "moondream_2", "moondream_2_docci"]
        show = model in llava_and_moondream_models

        self.prompt_label.setVisible(show)
        self.prompt_input.setVisible(show)
        self.fal_include_caption_checkbox.setVisible(show)
        self.max_tokens_label.setVisible(show)
        self.max_tokens_input.setVisible(show)
        self.temp_label.setVisible(show)
        self.temp_slider.setVisible(show)
        self.temp_value.setVisible(show)
        self.top_p_label.setVisible(show)
        self.top_p_slider.setVisible(show)
        self.top_p_value.setVisible(show)
        self.repetition_penalty_label.setVisible(show)
        self.repetition_penalty_slider.setVisible(show)
        self.repetition_penalty_value.setVisible(show)

    def reset_generation_status(self):
        if hasattr(self, 'generation_status'):
            self.generation_status.setText("Status: Ready")
            self.local_status_label.setText("Status: Ready")

    def on_provider_changed(self, provider):
        if provider == "Fal":
            self.stacked_widget.setCurrentIndex(0)
        elif provider == "Local":
            self.stacked_widget.setCurrentIndex(1)
        else:  # OpenRouter
            self.stacked_widget.setCurrentIndex(2)

    def update_openrouter_temp_value(self):
        value = self.openrouter_temp_slider.value() / 100
        self.openrouter_temp_value.setText(f"{value:.2f}")
        
    def update_openrouter_rep_penalty_value(self):
        value = self.openrouter_rep_penalty_slider.value() / 100
        self.openrouter_rep_penalty_value.setText(f"{value:.2f}")

    def update_repetition_penalty_value(self):
        self.repetition_penalty_value.setText(f"{self.repetition_penalty_slider.value() / 100:.2f}")

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

    def open_batch_processing(self):
        if not self.image_files:
            QMessageBox.warning(self, "No Images", "Please load a directory with images first.")
            return
        dialog = BatchProcessingDialog(self)
        dialog.exec_()

    def update_caption(self, index, result):
        self.current_image_index = index
        self.load_current_image()

        caption_mode = self.local_caption_mode_dropdown.currentText()
        if caption_mode == "Append":
            current_text = self.text_edit.toPlainText()
            if current_text:
                new_text = f"{current_text}, {result}"
            else:
                new_text = result
        else:  # Replace
            new_text = result

        self.text_edit.setText(new_text)
        self.save_description()

    def generate_wd_caption(self, batch_mode=False):
        if not self.image_files:
            QMessageBox.warning(self, "No Image", "Please load an image first.")
            return

        if not batch_mode:
            self.local_status_label.setText("Status: Generating...")
            self.local_generate_button.setEnabled(False)
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
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
                    new_text = f"{current_text}, {result}"
                else:
                    new_text = result
            else:  # Replace
                new_text = result

            self.text_edit.setText(new_text)
            self.save_description()

            if not batch_mode:
                self.local_status_label.setText("Status: Generation Complete")
        except Exception as e:
            if not batch_mode:
                QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
                self.local_status_label.setText("Status: Generation Failed")
        finally:
            if not batch_mode:
                self.local_generate_button.setEnabled(True)
                self.prev_button.setEnabled(True)
                self.next_button.setEnabled(True)

    def generate_openrouter_caption(self):
        if not self.image_files:
            QMessageBox.warning(self, "No Image", "Please load an image first.")
            return
        
        prompt = self.openrouter_prompt_input.toPlainText()
        
        if self.openrouter_include_caption_checkbox.isChecked():
            current_caption = self.text_edit.toPlainText()
            prompt = prompt.replace("{caption}", f'"{current_caption}"')
        model = self.openrouter_models_dropdown.currentText()
        api_key = self.settings.value("openrouter_api_key", "")
        max_tokens = self.openrouter_max_tokens_input.value()
        temperature = self.openrouter_temp_slider.value() / 100
        repetition_penalty = self.openrouter_rep_penalty_slider.value() / 100
        
        if not api_key:
            QMessageBox.warning(self, "Missing API Key", "Please set your OpenRouter API key in the Settings.")
            return
        
        self.openrouter_status_label.setText("Status: Generating...")
        self.openrouter_generate_button.setEnabled(False)
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        QApplication.processEvents()
        
        try:
            output_text = self.openrouter_describe_image(prompt, model, api_key, max_tokens, temperature, repetition_penalty)
            
            caption_mode = self.caption_mode_dropdown.currentText()
            if caption_mode == "Append":
                current_text = self.text_edit.toPlainText()
                if current_text:
                    self.text_edit.setText(f"{current_text}\n\n{output_text}")
                else:
                    self.text_edit.setText(output_text)
            else:  # Replace
                self.text_edit.setText(output_text)
            
            self.openrouter_status_label.setText("Status: Generation Complete")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
            self.openrouter_status_label.setText("Status: Generation Failed")
        finally:
            self.openrouter_generate_button.setEnabled(True)
            self.prev_button.setEnabled(True)
            self.next_button.setEnabled(True)

    def openrouter_describe_image(self, prompt, model, api_key, max_tokens, temperature, repetition_penalty):
        models = {
            "llama-3.1-8B (free)": "meta-llama/llama-3.1-8b-instruct:free",
            "phi3-mini (free)": "microsoft/phi-3-mini-128k-instruct:free",
            "phi3-medium (free)": "microsoft/phi-3-medium-128k-instruct:free",
            "Gemma-2-9B (free)": "google/gemma-2-9b-it:free",
        }
        model_id = models.get(model, "meta-llama/llama-3.1-8b-instruct:free")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": f"https://github.com/BetaDoggo/Assisted-Image-Labeler",
            "X-Title": f"Assisted-Image-Labeler",
            "Content-Type": "application/json"
        }
       
        data = {
            "model": model_id,
            "messages": [
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                ]}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "repetition_penalty": repetition_penalty
        }
       
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
       
        return response.json()['choices'][0]['message']['content']

    def generate_fal_caption(self):
        if not self.image_files:
            QMessageBox.warning(self, "No Image", "Please load an image first.")
            return

        current_image = os.path.join(self.current_directory, self.image_files[self.current_image_index])
        prompt = self.prompt_input.toPlainText()
        
        if self.fal_include_caption_checkbox.isChecked():
            current_caption = self.text_edit.toPlainText()
            prompt = prompt.replace("{caption}", f'"{current_caption}"')
        max_tokens = self.max_tokens_input.value()
        temp = self.temp_slider.value() / 10
        top_p = self.top_p_slider.value() / 10
        repetition_penalty = self.repetition_penalty_slider.value() / 100
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
            output_text = self.fal_describe_image(current_image, prompt, max_tokens, temp, top_p, model, api_key, repetition_penalty)

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

    def fal_describe_image(self, image_path, prompt, max_tokens, temp, top_p, model, api_key, repetition_penalty=1):
        # Set api key
        os.environ["FAL_KEY"] = api_key
        models = {
            "LLavaV15_13B": "fal-ai/llavav15-13b",
            "LLavaV16_34B": "fal-ai/llava-next",
            "Florence_2_Large": "fal-ai/florence-2-large/detailed-caption",
            "moondream_2": "fal-ai/moondream/batched",
            "moondream_2_docci": "fal-ai/moondream/batched" # these models share an endpoint
        }
        endpoint = models.get(model)
        if model == "moondream_2_docci":
            model_id = "fal-ai/moondream2-docci"
        else:
            model_id = "vikhyatk/moondream2"
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
        elif endpoint == "fal-ai/moondream/batched":
            handler = fal_client.submit(
                endpoint,
                arguments={
                    "model_id": model_id,
                    "inputs": [
                        {
                        "prompt": prompt,
                        "image_url": image_url,
                        }
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temp,
                    "top_p": top_p,
                    "repetition_penalty": repetition_penalty,
                })
            result = handler.get()
            output_text = result['outputs'][0]
        else: # llava
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
        self.prev_button.setToolTip("Previous image")

        self.next_button = QPushButton('', self)
        self.next_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowRight))
        self.next_button.clicked.connect(self.next_image)
        self.next_button.setToolTip("Next image")

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
        self.delete_button.setToolTip("Delete current image (Delete key)")
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
        save_button = QPushButton('Manual Save', self)
        save_button.clicked.connect(self.save_description)
        save_button.setToolTip("Save the caption (redundant if autosave is enabled)")
        next_unlabeled_button = QPushButton('Next Unlabeled', self)
        next_unlabeled_button.clicked.connect(self.next_unlabeled_image)
        next_unlabeled_button.setToolTip("Jump to the next unlabeled image")
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
        self.show_models_button.setToolTip("Toggle the Models tab")
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
        self.provider_dropdown.addItems(["Fal", "Local", "OpenRouter"])
        self.provider_dropdown.currentTextChanged.connect(self.on_provider_changed)
        provider_layout.addWidget(provider_label)
        provider_layout.addWidget(self.provider_dropdown)
        right_layout.addLayout(provider_layout)

        # Stacked widget for Providers
        self.stacked_widget = QStackedWidget()

        # Fal layout
        fal_widget = QWidget()
        fal_layout = QVBoxLayout(fal_widget)

        models_label = QLabel("Models:")
        self.models_dropdown = QComboBox()
        self.models_dropdown.addItems(["Florence_2_Large", "moondream_2", "moondream_2_docci", "LLavaV15_13B", "LLavaV16_34B"])
        fal_layout.addWidget(models_label)
        fal_layout.addWidget(self.models_dropdown)
        self.models_dropdown.currentTextChanged.connect(self.toggle_model_options)

        self.prompt_label = QLabel("Prompt:")
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Enter prompt here...")
        fal_layout.addWidget(self.prompt_label)
        fal_layout.addWidget(self.prompt_input)

        self.fal_include_caption_checkbox = QCheckBox("Replace {caption}")
        self.fal_include_caption_checkbox.setToolTip("Replace {caption} in the prompt with the current caption text")
        self.fal_include_caption_checkbox.setChecked(True)
        fal_layout.addWidget(self.fal_include_caption_checkbox)

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
        
        self.repetition_penalty_label = QLabel("Repetition Penalty:")
        self.repetition_penalty_slider = QSlider(Qt.Horizontal)
        self.repetition_penalty_slider.setRange(100, 150)
        self.repetition_penalty_slider.setValue(100)
        self.repetition_penalty_value = QLabel("1.00")
        repetition_penalty_layout = QHBoxLayout()
        repetition_penalty_layout.addWidget(self.repetition_penalty_slider)
        repetition_penalty_layout.addWidget(self.repetition_penalty_value)
        fal_layout.addWidget(self.repetition_penalty_label)
        fal_layout.addLayout(repetition_penalty_layout)
        self.repetition_penalty_slider.valueChanged.connect(self.update_repetition_penalty_value)

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

        # Add Batch button
        self.fal_batch_process_button = QPushButton("Batch Processing")
        self.fal_batch_process_button.clicked.connect(self.open_batch_processing)
        fal_layout.addWidget(self.fal_batch_process_button)

        self.toggle_model_options(self.models_dropdown.currentText()) # set visible items (Must be after loading all elements)
        
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

        # Add Batch button
        self.batch_process_button = QPushButton("Batch Processing")
        self.batch_process_button.clicked.connect(self.open_batch_processing)
        Local_layout.addWidget(self.batch_process_button)

        Local_layout.addStretch(1)
        self.stacked_widget.addWidget(Local_widget)

        right_layout.addWidget(self.stacked_widget)
        right_layout.addStretch(1)  # Push everything to the top
    
        self.right_panel.hide()  # Initially hidden
        main_layout.addWidget(self.right_panel, 3)  # Giving less space to the right panel

        # OpenRouter layout
        openrouter_widget = QWidget()
        openrouter_layout = QVBoxLayout(openrouter_widget)
        
        models_label = QLabel("Models:")
        self.openrouter_models_dropdown = QComboBox()
        self.openrouter_models_dropdown.addItems(["llama-3.1-8B (free)", "Gemma-2-9B (free)", "phi3-mini (free)", "phi3-medium (free)"])
        openrouter_layout.addWidget(models_label)
        openrouter_layout.addWidget(self.openrouter_models_dropdown)
        
        self.openrouter_prompt_label = QLabel("Prompt:")
        self.openrouter_prompt_input = QTextEdit()
        self.openrouter_prompt_input.setPlaceholderText("Enter prompt here...")
        openrouter_layout.addWidget(self.openrouter_prompt_label)
        openrouter_layout.addWidget(self.openrouter_prompt_input)
        
        self.openrouter_include_caption_checkbox = QCheckBox("Replace {caption}")
        self.openrouter_include_caption_checkbox.setToolTip("Replace {caption} in the prompt with the current caption text")
        self.openrouter_include_caption_checkbox.setChecked(True)
        openrouter_layout.addWidget(self.openrouter_include_caption_checkbox)

        # Add max_tokens input
        max_tokens_layout = QHBoxLayout()
        max_tokens_label = QLabel("Max Tokens:")
        self.openrouter_max_tokens_input = QSpinBox()
        self.openrouter_max_tokens_input.setRange(1, 2048)
        self.openrouter_max_tokens_input.setValue(256)
        max_tokens_layout.addWidget(max_tokens_label)
        max_tokens_layout.addWidget(self.openrouter_max_tokens_input)
        openrouter_layout.addLayout(max_tokens_layout)
        
        # Add temperature slider
        temp_layout = QHBoxLayout()
        temp_label = QLabel("Temperature:")
        self.openrouter_temp_slider = QSlider(Qt.Horizontal)
        self.openrouter_temp_slider.setRange(0, 200)
        self.openrouter_temp_slider.setValue(70)
        self.openrouter_temp_value = QLabel("0.7")
        temp_layout.addWidget(temp_label)
        temp_layout.addWidget(self.openrouter_temp_slider)
        temp_layout.addWidget(self.openrouter_temp_value)
        openrouter_layout.addLayout(temp_layout)
        self.openrouter_temp_slider.valueChanged.connect(self.update_openrouter_temp_value)
        
        # Add repetition_penalty slider
        rep_penalty_layout = QHBoxLayout()
        rep_penalty_label = QLabel("Repetition Penalty:")
        self.openrouter_rep_penalty_slider = QSlider(Qt.Horizontal)
        self.openrouter_rep_penalty_slider.setRange(1, 200)
        self.openrouter_rep_penalty_slider.setValue(100)
        self.openrouter_rep_penalty_value = QLabel("1.00")
        rep_penalty_layout.addWidget(rep_penalty_label)
        rep_penalty_layout.addWidget(self.openrouter_rep_penalty_slider)
        rep_penalty_layout.addWidget(self.openrouter_rep_penalty_value)
        openrouter_layout.addLayout(rep_penalty_layout)
        self.openrouter_rep_penalty_slider.valueChanged.connect(self.update_openrouter_rep_penalty_value)
        
        self.openrouter_status_label = QLabel("Status: Ready")
        openrouter_layout.addWidget(self.openrouter_status_label)
        
        self.openrouter_generate_button = QPushButton("Generate Caption")
        self.openrouter_generate_button.clicked.connect(self.generate_openrouter_caption)
        openrouter_layout.addWidget(self.openrouter_generate_button)

        self.openrouter_batch_process_button = QPushButton("Batch Processing")
        self.openrouter_batch_process_button.clicked.connect(self.open_batch_processing)
        openrouter_layout.addWidget(self.openrouter_batch_process_button)
        
        openrouter_layout.addStretch(1)
        self.stacked_widget.addWidget(openrouter_widget)

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
        if dialog.exec_():
            self.apply_theme()

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
        if self.image_files:
            if self.should_autosave():
                self.save_description()
            self.current_image_index = (self.current_image_index - 1) % len(self.image_files)
            self.load_current_image()

    def next_image(self):
        if self.image_files:
            if self.should_autosave():
                self.save_description()
            self.current_image_index = (self.current_image_index + 1) % len(self.image_files)
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

    def apply_theme(self):
        theme = self.settings.value("theme", "Dark")
        if theme == "Dark":
            self.set_dark_theme()
        elif theme == "Light":
            self.set_light_theme()
        elif theme == "Lime":
            self.set_lime_theme()

    def set_dark_theme(self):
        app = QApplication.instance()
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

    def set_light_theme(self):
        app = QApplication.instance()
        app.setStyle(QStyleFactory.create("Fusion"))
        app.setPalette(app.style().standardPalette())

    def set_lime_theme(self):
        app = QApplication.instance()
        app.setStyle(QStyleFactory.create("Fusion"))
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(255, 192, 203))  # Pink
        palette.setColor(QPalette.WindowText, Qt.black)
        palette.setColor(QPalette.Base, QColor(50, 205, 50))  # Lime Green
        palette.setColor(QPalette.AlternateBase, QColor(200, 255, 200))
        palette.setColor(QPalette.ToolTipBase, Qt.white)
        palette.setColor(QPalette.ToolTipText, Qt.black)
        palette.setColor(QPalette.Text, Qt.black)
        palette.setColor(QPalette.Button, QColor(50, 205, 50))  # Lime Green
        palette.setColor(QPalette.ButtonText, Qt.black)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.HighlightedText, Qt.white)
        app.setPalette(palette)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ImageTextPairApp()
    ex.show()
    sys.exit(app.exec_())