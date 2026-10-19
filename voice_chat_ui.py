import queue
import threading
import tkinter as tk
from tkinter import scrolledtext

import numpy as np
import ollama
import sounddevice as sd
from faster_whisper import WhisperModel

MODEL = "llama3.2:1b"    # any model you've pulled with `ollama pull`
SAMPLE_RATE = 16000
SYSTEM_PROMPT = (
    "You are the user's friend. Talk casually and warmly, like a friend would in a "
    "conversation. Answer whatever they ask honestly and helpfully. Keep replies short "
    "and natural, since this is a spoken-style chat."
)


class VoiceChatApp:
    def __init__(self, root):
        self.root = root
        self.history = []
        self.stt = None
        self.recording = False
        self.frames = []
        self.stream = None
        self.busy = False
        self.events = queue.Queue()   # worker threads -> UI thread

        root.title(f"Voice Chat ({MODEL})")
        root.geometry("640x520")

        self.chat = scrolledtext.ScrolledText(root, wrap=tk.WORD, state=tk.DISABLED,
                                              font=("Segoe UI", 11), padx=8, pady=8)
        self.chat.tag_config("you", foreground="#1a5fb4", font=("Segoe UI", 11, "bold"))
        self.chat.tag_config("ai", foreground="#26a269", font=("Segoe UI", 11, "bold"))
        self.chat.tag_config("info", foreground="#888888", font=("Segoe UI", 9, "italic"))
        self.chat.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))

        bar = tk.Frame(root)
        bar.pack(fill=tk.X, padx=8, pady=4)
        self.entry = tk.Entry(bar, font=("Segoe UI", 11))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self.send_typed())
        tk.Button(bar, text="Send", command=self.send_typed).pack(side=tk.LEFT, padx=(4, 0))

        controls = tk.Frame(root)
        controls.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.mic_btn = tk.Button(controls, text="🎤 Start talking", width=18,
                                 command=self.toggle_recording, state=tk.DISABLED)
        self.mic_btn.pack(side=tk.LEFT)
        tk.Button(controls, text="Clear chat", command=self.clear).pack(side=tk.LEFT, padx=4)
        self.status = tk.Label(controls, text="Loading speech model...", fg="#888888")
        self.status.pack(side=tk.RIGHT)

        threading.Thread(target=self.load_stt, daemon=True).start()
        root.after(50, self.process_events)

    # ---------- background work ----------

    def load_stt(self):
        # runs on CPU, downloads on first use
        self.stt = WhisperModel("base.en", device="cpu", compute_type="int8")
        self.events.put(("ready", None))

    def transcribe(self, audio):
        segments, _ = self.stt.transcribe(audio, language="en")
        text = " ".join(s.text.strip() for s in segments).strip()
        self.events.put(("heard", text))

    def ask_model(self):
        reply = ""
        try:
            for chunk in ollama.chat(model=MODEL, stream=True,
                                     messages=[{"role": "system", "content": SYSTEM_PROMPT}] + self.history):
                piece = chunk["message"]["content"]
                reply += piece
                self.events.put(("piece", piece))
        except Exception as e:
            self.events.put(("error", str(e)))
        self.history.append({"role": "assistant", "content": reply})
        self.events.put(("done", None))

    # ---------- UI thread ----------

    def process_events(self):
        while not self.events.empty():
            kind, data = self.events.get()
            if kind == "ready":
                self.mic_btn.config(state=tk.NORMAL)
                self.set_status("Ready")
            elif kind == "heard":
                if data:
                    self.submit(data)
                else:
                    self.write("(heard nothing)\n", "info")
                    self.set_busy(False)
            elif kind == "piece":
                self.write(data)
            elif kind == "error":
                self.write(f"\n[error: {data}]", "info")
            elif kind == "done":
                self.write("\n\n")
                self.set_busy(False)
        self.root.after(50, self.process_events)

    def toggle_recording(self):
        if not self.recording:
            self.frames = []
            self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                         callback=lambda data, *_: self.frames.append(data.copy()))
            self.stream.start()
            self.recording = True
            self.mic_btn.config(text="⏹ Stop", bg="#e01b24", fg="white")
            self.set_status("Listening...")
        else:
            self.stream.stop()
            self.stream.close()
            self.recording = False
            self.mic_btn.config(text="🎤 Start talking", bg="SystemButtonFace", fg="black")
            if not self.frames:
                return
            audio = np.squeeze(np.concatenate(self.frames))
            self.set_busy(True, "Transcribing...")
            threading.Thread(target=self.transcribe, args=(audio,), daemon=True).start()

    def send_typed(self):
        text = self.entry.get().strip()
        if text and not self.busy:
            self.entry.delete(0, tk.END)
            self.set_busy(True)
            self.submit(text)

    def submit(self, text):
        self.write("You: ", "you")
        self.write(text + "\n")
        self.write("AI: ", "ai")
        self.history.append({"role": "user", "content": text})
        self.set_status("Thinking...")
        threading.Thread(target=self.ask_model, daemon=True).start()

    def set_busy(self, busy, status=None):
        self.busy = busy
        state = tk.DISABLED if busy or self.stt is None else tk.NORMAL
        self.mic_btn.config(state=state)
        self.set_status(status or ("Working..." if busy else "Ready"))

    def set_status(self, text):
        self.status.config(text=text)

    def write(self, text, tag=None):
        self.chat.config(state=tk.NORMAL)
        self.chat.insert(tk.END, text, tag)
        self.chat.see(tk.END)
        self.chat.config(state=tk.DISABLED)

    def clear(self):
        if self.busy:
            return
        self.history.clear()
        self.chat.config(state=tk.NORMAL)
        self.chat.delete("1.0", tk.END)
        self.chat.config(state=tk.DISABLED)


if __name__ == "__main__":
    root = tk.Tk()
    VoiceChatApp(root)
    root.mainloop()
