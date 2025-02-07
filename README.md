# Transcription Speed Tester

## Overview

This is a desktop application that allows you to record audio and compare transcription speeds and accuracy across two different AI transcription services: Groq Cloud and Deepgram.

## Features

- 🎙️ Audio Recording: Press and hold the SPACE key to record audio
- 🤖 Dual Transcription: Automatically transcribes the recording using:
  - Groq Cloud (distil-whisper-large-v3-en)
  - Deepgram (nova-3)
- ⏱️ Speed Measurement: Shows transcription time for each service
- 🔍 Interactive Accuracy Tracking: 
  - Click on individual words to mark them as inaccurate
  - Real-time accuracy percentage calculation
- 🔑 Flexible API Key Input: Enter your own Groq and Deepgram API keys

## Prerequisites

- Python 3.7+
- API Keys:
  - Groq Cloud API Key
  - Deepgram API Key

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Run the application:
   ```bash
   python app.py
   ```
2. Enter your Groq and Deepgram API keys
3. Press and hold SPACE to start recording
4. Release SPACE to stop recording and start transcription
5. Click on words to mark them as inaccurate
6. View transcription speed and accuracy for each service

## How It Works

- When you press SPACE, the app starts recording audio
- Upon releasing SPACE, it saves the recording as a WAV file
- Sends the audio to Groq Cloud and Deepgram for transcription
- Displays transcription results side by side
- Allows interactive accuracy tracking by clicking on words

## Accuracy Tracking

- Each word is a clickable label
- Click a word to mark it as inaccurate
- Accuracy percentage updates in real-time
- Shows the number of correct words out of total words

## Requirements

See `requirements.txt` for a full list of Python dependencies.

## License

[Add your license here]

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 