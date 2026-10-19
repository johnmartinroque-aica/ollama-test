# Ollama Voice Chat

A small desktop chat app that lets you talk to a local AI model using your voice or the keyboard. Everything runs on your own computer, and no internet is needed after setup.

- **Speech-to-text:** [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (`base.en` model, runs on CPU)
- **AI replies:** [Ollama](https://ollama.com) (default model: `llama3.2:1b`)
- **Interface:** Tkinter

## Features

- 🎤 Click to talk, click again to stop. Your speech is transcribed and sent to the AI.
- ⌨️ Or type a message and press **Enter**.
- Replies appear word by word as the model writes them.
- The AI remembers the conversation until you click **Clear chat**.
- The AI acts as a casual, friendly chat partner and keeps its replies short.

## Requirements

- Python 3.10 or newer
- [Ollama](https://ollama.com/download) installed and running
- A microphone

## Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/johnmartinroque-aica/ollama-test.git
   cd ollama-test
   ```

2. **Create and activate a virtual environment**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS / Linux
   source venv/bin/activate
   ```

3. **Install the dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Download the AI model**
   ```bash
   ollama pull llama3.2:1b
   ```

## Usage

```bash
python voice_chat_ui.py
```

The first launch downloads the Whisper speech model (about 150 MB), so it may take a minute. The status shows **Ready** when it's done and the 🎤 button becomes clickable.

## Configuration

Edit the top of `voice_chat_ui.py`:

| Setting | What it does |
|---|---|
| `MODEL` | The Ollama model to use. Any model you've pulled works, e.g. `llama3.2:3b` |
| `SYSTEM_PROMPT` | The AI's personality and instructions |
| `SAMPLE_RATE` | Microphone sample rate (leave at `16000` for Whisper) |

## Troubleshooting

- **`[error: ...]` in the chat:** Make sure Ollama is running and that you've pulled the model named in `MODEL`.
- **"(heard nothing)":** Check that your microphone is the default input device and isn't muted.
- **Slow replies:** Try a smaller model, or use a computer with a GPU.
