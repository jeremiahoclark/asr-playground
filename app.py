#!/usr/bin/env python3
"""
A Python application that records audio when you press SPACE,
sends the recording to two transcription services (Groq Cloud's
distil-whisper-large-v3-en and Deepgram's nova-3), shows the speed
of each transcription, displays the transcript (with each word clickable
to mark it as inaccurate) and recalculates accuracy.

Before running, install the requirements listed in requirements.txt.
"""

import sys
import time
import threading
import wave
import requests

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QScrollArea, QPushButton, QLayout, QLineEdit
)
from PyQt5.QtCore import Qt, QSize, QRect, QPoint, pyqtSignal, QThread
from PyQt5.QtGui import QFont
import pyaudio

# -------------------------------------------------------------
# FlowLayout (adapted from Qt's Flow Layout Example)
# -------------------------------------------------------------
class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=-1):
        super(FlowLayout, self).__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.itemList.append(item)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self.doLayout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super(FlowLayout, self).setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0

        for item in self.itemList:
            widget = item.widget()
            spaceX = self.spacing()
            spaceY = self.spacing()
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y()

# -------------------------------------------------------------
# ClickableLabel: Each word is a label that toggles when clicked.
# -------------------------------------------------------------
class ClickableLabel(QLabel):
    toggled = pyqtSignal(bool)  # Emits True if marked as inaccurate, False if unmarked.

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.selected = False
        self.setStyleSheet("border: 1px solid gray; padding: 2px; margin: 2px;")
    
    def mousePressEvent(self, event):
        self.selected = not self.selected
        if self.selected:
            self.setStyleSheet("background-color: yellow; border: 1px solid gray; padding: 2px; margin: 2px;")
        else:
            self.setStyleSheet("background-color: none; border: 1px solid gray; padding: 2px; margin: 2px;")
        self.toggled.emit(self.selected)

# -------------------------------------------------------------
# TranscriptionWidget: Displays API name, transcription speed,
# transcript (with clickable words), and accuracy calculation.
# -------------------------------------------------------------
class TranscriptionWidget(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.title = title
        self.word_labels = []

        layout = QVBoxLayout(self)
        self.titleLabel = QLabel(title)
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)
        self.titleLabel.setFont(font)
        layout.addWidget(self.titleLabel)

        self.speedLabel = QLabel("Speed: -")
        layout.addWidget(self.speedLabel)

        # Scrollable area for transcript words
        self.scrollArea = QScrollArea()
        self.scrollAreaWidget = QWidget()
        self.flowLayout = FlowLayout(self.scrollAreaWidget)
        self.scrollAreaWidget.setLayout(self.flowLayout)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setWidget(self.scrollAreaWidget)
        layout.addWidget(self.scrollArea)

        self.accuracyLabel = QLabel("Accuracy: -")
        layout.addWidget(self.accuracyLabel)

        self.setLayout(layout)

    def set_transcription(self, text, speed):
        self.speedLabel.setText(f"Speed: {speed:.2f} seconds")
        # Clear previous words
        for i in reversed(range(self.flowLayout.count())):
            item = self.flowLayout.takeAt(i)
            if item:
                widget = item.widget()
                if widget:
                    widget.deleteLater()
        self.word_labels = []

        words = text.split()
        for word in words:
            label = ClickableLabel(word)
            label.toggled.connect(self.update_accuracy)
            self.flowLayout.addWidget(label)
            self.word_labels.append(label)
        self.update_accuracy()

    def update_accuracy(self, *args):
        total = len(self.word_labels)
        if total == 0:
            accuracy_text = "Accuracy: N/A"
        else:
            inaccurate = sum(1 for label in self.word_labels if label.selected)
            accuracy = ((total - inaccurate) / total) * 100
            accuracy_text = f"Accuracy: {accuracy:.1f}% ({total - inaccurate}/{total} correct)"
        self.accuracyLabel.setText(accuracy_text)

# -------------------------------------------------------------
# Worker threads for API calls
# -------------------------------------------------------------
class GroqWorker(QThread):
    result_ready = pyqtSignal(str, float)  # (transcription, elapsed time)

    def __init__(self, audio_file, groq_api_key):
        super().__init__()
        self.audio_file = audio_file
        self.groq_api_key = groq_api_key

    def run(self):
        try:
            url = "https://api.groq.com/openai/v1/audio/transcriptions"
            headers = {"Authorization": f"Bearer {self.groq_api_key}"}
            # Note: Although the example uses an .m4a file, here we send our WAV file.
            files = {
                "model": (None, "distil-whisper-large-v3-en"),
                "file": (self.audio_file, open(self.audio_file, "rb")),
                "response_format": (None, "verbose_json")
            }
            start_time = time.time()
            response = requests.post(url, headers=headers, files=files)
            elapsed = time.time() - start_time
            data = response.json()
            transcription = data.get("text", "")
        except Exception as e:
            transcription = f"Error: {e}"
            elapsed = 0.0
        self.result_ready.emit(transcription, elapsed)

class DeepgramWorker(QThread):
    result_ready = pyqtSignal(str, float)  # (transcription, elapsed time)

    def __init__(self, audio_file, deepgram_api_key):
        super().__init__()
        self.audio_file = audio_file
        self.deepgram_api_key = deepgram_api_key

    def run(self):
        try:
            url = "https://api.deepgram.com/v1/listen?model=nova-3&language=en"
            headers = {
                "Authorization": f"Token {self.deepgram_api_key}",
                "Content-Type": "audio/wav"
            }
            with open(self.audio_file, "rb") as f:
                audio_data = f.read()
            start_time = time.time()
            response = requests.post(url, headers=headers, data=audio_data)
            elapsed = time.time() - start_time
            data = response.json()
            # Navigate the returned JSON structure:
            transcription = (
                data.get("results", {})
                    .get("channels", [{}])[0]
                    .get("alternatives", [{}])[0]
                    .get("transcript", "")
            )
        except Exception as e:
            transcription = f"Error: {e}"
            elapsed = 0.0
        self.result_ready.emit(transcription, elapsed)

# -------------------------------------------------------------
# Main application window
# -------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Transcription Speed Tester")
        self.setGeometry(100, 100, 800, 600)

        # Recording state variables
        self.recording = False
        self.recording_thread = None
        self.stop_recording_event = threading.Event()
        self.audio_filename = "audio.wav"  # We record as WAV

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # ---------------------------------------------------------
        # API Key inputs added for open source usage
        # ---------------------------------------------------------
        api_keys_layout = QHBoxLayout()
        groq_key_label = QLabel("Groq API Key:")
        self.groqApiLineEdit = QLineEdit()
        self.groqApiLineEdit.setPlaceholderText("Enter Groq API Key")
        deepgram_key_label = QLabel("Deepgram API Key:")
        self.deepgramApiLineEdit = QLineEdit()
        self.deepgramApiLineEdit.setPlaceholderText("Enter Deepgram API Key")
        api_keys_layout.addWidget(groq_key_label)
        api_keys_layout.addWidget(self.groqApiLineEdit)
        api_keys_layout.addWidget(deepgram_key_label)
        api_keys_layout.addWidget(self.deepgramApiLineEdit)
        main_layout.addLayout(api_keys_layout)

        self.statusLabel = QLabel("Press SPACE to start recording.")
        main_layout.addWidget(self.statusLabel)

        # Create a horizontal layout for the two transcription panels
        transcriptions_layout = QHBoxLayout()
        self.groqWidget = TranscriptionWidget("Groq Cloud (distil-whisper-large-v3-en)")
        self.deepgramWidget = TranscriptionWidget("Deepgram (nova-3)")
        transcriptions_layout.addWidget(self.groqWidget)
        transcriptions_layout.addWidget(self.deepgramWidget)
        main_layout.addLayout(transcriptions_layout)

        # Optional Reset button
        self.resetButton = QPushButton("Reset")
        self.resetButton.clicked.connect(self.reset_transcriptions)
        main_layout.addWidget(self.resetButton)

    def reset_transcriptions(self):
        self.groqWidget.set_transcription("", 0)
        self.deepgramWidget.set_transcription("", 0)
        self.statusLabel.setText("Press SPACE to start recording.")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space and not self.recording:
            self.start_recording()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space and self.recording:
            self.stop_recording()
        else:
            super().keyReleaseEvent(event)

    def start_recording(self):
        self.recording = True
        self.statusLabel.setText("Recording while SPACE is held down...")
        self.stop_recording_event.clear()
        self.frames = []
        # Start audio recording in a separate thread
        self.recording_thread = threading.Thread(target=self.record_audio)
        self.recording_thread.start()

    def stop_recording(self):
        if not self.recording:  # Prevent multiple stops
            return
        self.recording = False
        self.stop_recording_event.set()
        self.recording_thread.join()
        self.statusLabel.setText("Processing transcriptions...")
        # Start API calls on the recorded file
        self.start_transcription()

    def record_audio(self):
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000

        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                        input=True, frames_per_buffer=CHUNK)
        self.frames = []

        while not self.stop_recording_event.is_set():
            try:
                data = stream.read(CHUNK)
            except Exception as e:
                print("Error recording audio:", e)
                break
            self.frames.append(data)

        stream.stop_stream()
        stream.close()
        p.terminate()

        # Save the recorded frames as a WAV file.
        wf = wave.open(self.audio_filename, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(self.frames))
        wf.close()

    def start_transcription(self):
        # Retrieve API keys from the input fields
        groq_api_key = self.groqApiLineEdit.text().strip()
        deepgram_api_key = self.deepgramApiLineEdit.text().strip()
        if not groq_api_key or not deepgram_api_key:
            self.statusLabel.setText("Please enter both API keys!")
            return

        # Run transcriptions sequentially
        self.statusLabel.setText("Starting Groq Cloud transcription...")
        self.groqWorker = GroqWorker(self.audio_filename, groq_api_key)
        self.groqWorker.result_ready.connect(self.handle_groq_result)
        self.groqWorker.finished.connect(self.start_deepgram_transcription)
        self.groqWorker.start()

    def start_deepgram_transcription(self):
        self.statusLabel.setText("Starting Deepgram transcription...")
        deepgram_api_key = self.deepgramApiLineEdit.text().strip()
        self.deepgramWorker = DeepgramWorker(self.audio_filename, deepgram_api_key)
        self.deepgramWorker.result_ready.connect(self.handle_deepgram_result)
        self.deepgramWorker.start()

    def handle_groq_result(self, transcription, speed):
        self.groqWidget.set_transcription(transcription, speed)
        self.statusLabel.setText("Groq Cloud transcription complete. Starting Deepgram...")

    def handle_deepgram_result(self, transcription, speed):
        self.deepgramWidget.set_transcription(transcription, speed)
        self.statusLabel.setText("All transcriptions complete. Press SPACE to start a new recording.")

# -------------------------------------------------------------
# Main entry point
# -------------------------------------------------------------
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
