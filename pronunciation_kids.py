import difflib
import os
import queue
import re
import subprocess
import threading
import tkinter as tk

import numpy as np
import ollama
import pronouncing
import sounddevice as sd
from faster_whisper import WhisperModel

from pronunciation_data import PAIRS, SOUNDS_LIKE

MODEL = "llama3.2:1b"    # any model you've pulled with `ollama pull`
SAME_SOUND = {word: group[0] for group in SOUNDS_LIKE for word in group}
SAMPLE_RATE = 16000
SILENCE_LEVEL = 0.01    # peak amplitude below this counts as "heard nothing"
FONT = "Segoe UI"
BG = "#fff8e7"
GOLD = "#f5a623"
GREEN = "#2e9e44"
RED = "#d6336c"
BORDER = "#e0d6c0"

# The stars and the tip are worked out in code so they're always right;
# the model only turns them into friendly words.
COACH_PROMPT = """You are Coach Sunny, a kind English pronunciation coach for children aged 5 to 10 whose first language is Japanese.

You get a short report about the child's last try. Write what you will say to the child.

Rules:
- At most 2 short sentences and 30 words.
- Easy words only. Talk to the child as "you".
- If "Correct: no", do NOT praise the word. Say kindly what it sounded like, then give the tip.
- If "Correct: yes", cheer and name the word.
- Use the tip from the report. Keep its sound names and mouth moves exactly. Do not invent other tips.
- Never say "wrong", "bad" or "fail". Never mention stars, scores or computers. No emojis."""

# small models follow examples far better than rules
COACH_EXAMPLES = [
    ("Word to say: rice\nCorrect: no\nIt sounded like: rise\n"
     "Tip: rice ends with S, a quiet snake sound, sss. rise ends with Z, a buzzy bee sound, zzz.",
     "Oops, that sounded like rise! End rice with a quiet snake sound, sss, not a buzzy zzz."),
    ("Word to say: right\nCorrect: no\nIt sounded like: light\n"
     "Tip: right starts with R, your tongue floats and does not touch the top of your mouth. "
     "light starts with L, your tongue tip touches behind your top front teeth.",
     "Hmm, I heard light. For right, let your tongue float and not touch the top of your mouth."),
    ("Word to say: load\nCorrect: yes\nGood sound: L",
     "Wow, load sounded super clear! Great L sound!"),
    ("Word to say: right\nCorrect: yes\nGood sound: R",
     "Yay, I heard right! Your R sound was super!"),
    ("Tongue twister: Roll down the road with a light load.\nCorrect: almost\n"
     "Missed word: roll, it sounded like: low\n"
     "Tip: roll starts with R, your tongue floats and does not touch the top of your mouth.",
     "So close! For roll, let your tongue float at the start, not touching the top of your mouth."),
]

# ARPAbet phoneme (CMU dictionary) -> (name a child can follow, how to make it)
PHONEMES = {
    "R": ("R", "your tongue floats and does not touch the top of your mouth"),
    "L": ("L", "your tongue tip touches behind your top front teeth"),
    "S": ("S", "a quiet snake sound, sss"),
    "Z": ("Z", "a buzzy bee sound, zzz"),
    "TH": ("TH as in thank", "your tongue peeks out between your teeth and you blow"),
    "DH": ("TH as in this", "your tongue peeks out between your teeth and you buzz"),
    "F": ("F", "your top teeth rest on your bottom lip and you blow"),
    "V": ("V", "your top teeth rest on your bottom lip and you buzz"),
    "B": ("B", "your lips press together and pop with your voice on"),
    "P": ("P", "your lips press together and pop a little puff of air"),
    "M": ("M", "your lips close and you hum, mmm"),
    "N": ("N", "your tongue tip goes up behind your top teeth and you hum"),
    "NG": ("NG as in sing", "the back of your tongue goes up and you hum"),
    "D": ("D", "your tongue taps behind your top teeth with your voice on"),
    "T": ("T", "your tongue taps behind your top teeth with a puff of air"),
    "G": ("G", "the back of your tongue pops with your voice on"),
    "K": ("K", "the back of your tongue pops with a puff of air"),
    "SH": ("SH", "your lips push out for a quiet shhh"),
    "ZH": ("ZH as in treasure", "your lips push out and you buzz"),
    "CH": ("CH", "a quick choo, like a sneeze"),
    "JH": ("J", "your lips push out for a buzzy j, as in jump"),
    "W": ("W", "your lips make a small circle, then open"),
    "Y": ("Y", "you start like saying yes"),
    "HH": ("H", "a soft breath out, like fogging a window"),
    "IY": ("long EE as in see", "smile wide and make it long"),
    "IH": ("short I as in sit", "relax your mouth and make it quick"),
    "EH": ("E as in bed", "open your mouth a little"),
    "AE": ("A as in cat", "open your mouth wide"),
    "AA": ("AH as in father", "open your mouth tall"),
    "AH": ("UH as in cup", "relax your mouth for a short uh"),
    "AO": ("AW as in saw", "open tall with round lips"),
    "OW": ("OH as in go", "round your lips and slide to oo"),
    "UH": ("short OO as in book", "round your lips a little and make it quick"),
    "UW": ("long OO as in moon", "push your lips out small and round"),
    "ER": ("ER as in her", "pull your tongue back, like a little growl"),
    "AY": ("I as in bike", "slide from ah to ee"),
    "EY": ("A as in day", "slide from eh to ee"),
    "AW": ("OW as in cow", "slide from ah to oo"),
    "OY": ("OY as in boy", "slide from oh to ee"),
}
VOWELS = {"IY", "IH", "EH", "AE", "AA", "AH", "AO", "OW", "UH", "UW", "ER", "AY", "EY", "AW", "OY"}


def clean(token):
    return "".join(re.findall(r"[a-z']+", token.lower()))


def sound(word):
    # "lies" -> "lice", "write" -> "right": we grade the sound, not the spelling
    return SAME_SOUND.get(word, word)


def words(text):
    return [sound(w) for w in (clean(t) for t in text.split()) if w]


def speak(text):
    # Windows built-in voice, nothing extra to install
    script = ("Add-Type -AssemblyName System.Speech; "
              "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              "$s.Rate = -3; $s.Speak($env:SAY_TEXT)")
    subprocess.run(["powershell", "-NoProfile", "-Command", script],
                   env={**os.environ, "SAY_TEXT": text},
                   creationflags=subprocess.CREATE_NO_WINDOW)


def check_word(heard, target, other):
    said = words(heard)
    if sound(target) in said:
        return 3, f"Great job! I heard “{target}”!"
    if sound(other) in said:
        return 0, f"That sounded like “{other}”. Try again!"
    return 0, f"I heard “{heard}”. Try again!"


def check_twister(heard, target):
    expected, said = words(target), words(heard)
    matcher = difflib.SequenceMatcher(None, expected, said, autojunk=False)
    hits = set()
    for a, _, size in matcher.get_matching_blocks():
        hits.update(range(a, a + size))
    ratio = len(hits) / len(expected)
    # one swapped R/L word is the mistake we're practising, so 3 stars needs all words
    stars = 3 if ratio == 1 else 2 if ratio >= 0.75 else 1 if ratio >= 0.4 else 0
    message = {3: "Amazing!", 2: "Very good!", 1: "Nice try!", 0: "Let's try again!"}[stars]
    return stars, f"{message}  I heard: “{heard}”", hits


def phones(word):
    found = pronouncing.phones_for_word(word)
    return [re.sub(r"\d", "", p) for p in found[0].split()] if found else None


def name(phone):
    return PHONEMES.get(phone, (phone, ""))[0]


def describe(word, sounds, index, instead=None):
    # "rice ends with S, not Z: a quiet snake sound, sss"  "grass has R after the G: ..."
    where = (f"starts with {name(sounds[index])}" if index == 0
             else f"ends with {name(sounds[index])}" if index == len(sounds) - 1
             else f"has {name(sounds[index])} after the {name(sounds[index - 1])}")
    not_that = f", not {name(instead)}" if instead else ""
    return f"{word} {where}{not_that}: {PHONEMES.get(sounds[index], ('', 'listen closely'))[1]}"


def sound_tip(target, heard):
    # Find the first sound that differs, e.g. rice (R AY S) vs rise (R AY Z) -> S vs Z.
    # Returns (full tip for the model, short tip for the built-in reply).
    t, h = phones(target), phones(heard) if heard else None
    if not t or not h:
        return None
    for op, i1, _, j1, _ in difflib.SequenceMatcher(None, t, h, autojunk=False).get_opcodes():
        if op == "replace":
            return (f"{describe(target, t, i1)}. {describe(heard, h, j1)}.",
                    f"{describe(target, t, i1, h[j1])}.")
        if op == "delete":
            mine = f"{describe(target, t, i1)}. Don't skip the {name(t[i1])} sound."
            return mine, mine
        if op == "insert":
            extra = "an extra vowel" if h[j1] in VOWELS else f"an extra {name(h[j1])}"
            mine = f"{target} has no {name(h[j1])} sound, so try not to add {extra}."
            return mine, mine
    return None


def key_sound(word, other):
    # the sound that tells the pair apart, for praise like "Great R sound!"
    t, o = phones(word), phones(other)
    if t and o:
        for op, i1, _, _, _ in difflib.SequenceMatcher(None, t, o, autojunk=False).get_opcodes():
            if op in ("replace", "delete"):
                return name(t[i1])
    return None


def first_sound_tip(word, pair):
    # skipped or unknown word: teach its first sound, else the teacher's note
    sounds = phones(word)
    tip = describe(word, sounds, 0) + "." if sounds else pair["tongueTwister"]["note"]["en"]
    return tip, tip


def closest(target, candidates):
    # the heard word that sounds most like the target, e.g. "rise" out of "I rise"
    t = phones(target)
    known = [w for w in candidates if phones(w)]
    if not t or not known:
        return candidates[0] if candidates else None
    return max(known, key=lambda w: difflib.SequenceMatcher(None, t, phones(w)).ratio())


def coach_message(pair, kind, heard, stars):
    # The code decides what happened and which tip fits; the model only words it.
    # Returns (report for the model, built-in reply if the model can't be trusted).
    if kind == "twister":
        text = pair["tongueTwister"]["text"]
        expected = [clean(t) for t in text.split() if clean(t)]
        said = [clean(t) for t in heard.split() if clean(t)]
        lines = [f"Tongue twister: {text}"]
        if stars == 3:
            return "\n".join(lines + ["Correct: yes"]), "Amazing! You said every word clearly!"
        # pair each missed word with whatever was said in its place
        swaps = []
        matcher = difflib.SequenceMatcher(None, [sound(w) for w in expected],
                                          [sound(w) for w in said], autojunk=False)
        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op in ("replace", "delete"):
                for k in range(i1, i2):
                    swaps.append((expected[k], said[j1 + k - i1] if j1 + k - i1 < j2 else None))
        word, instead = swaps[0] if swaps else (expected[0], None)
        tip, short = sound_tip(word, instead) or first_sound_tip(word, pair)
        lines.append("Correct: almost" if stars == 2 else "Correct: no")
        lines.append(f"Missed word: {word}, it sounded like: {instead}" if instead
                     else f"Missed word: {word}, it was skipped")
        lines.append(f"Tip: {tip}")
        opener = "So close!" if stars == 2 else "Nice try!"
        return "\n".join(lines), f"{opener} {capital(short)}"

    target = pair[kind]
    other = pair["wordB" if kind == "wordA" else "wordA"]
    lines = [f"Word to say: {target}"]
    if stars:
        good = key_sound(target, other)
        lines += ["Correct: yes"] + ([f"Good sound: {good}"] if good else [])
        return "\n".join(lines), f"Yay! {capital(target)} sounded super clear!"
    said = [clean(t) for t in heard.split() if clean(t)]
    instead = other if sound(other) in [sound(w) for w in said] else closest(target, said)
    # if we don't know the heard word, teach the sound that makes this pair different
    tip, short = (sound_tip(target, instead) or sound_tip(target, other)
                  or first_sound_tip(target, pair))
    lines += ["Correct: no", f"It sounded like: {instead}", f"Tip: {tip}"]
    return "\n".join(lines), f"Oops, that sounded like {instead}. {capital(short)}"


def capital(text):
    return text[:1].upper() + text[1:]


PRAISE = re.compile(r"\b(perfect|correct|clearly|you'?re right|you are right|you got it|"
                    r"well done|great job|excellent|nailed|good job)\b", re.I)
RETRY = re.compile(r"\b(sounded like|sounds like|try again|oops|instead|not quite|almost|"
                   r"close|you'?re right|you are right|tongue|lips|teeth)\b", re.I)
FILLER = {"your", "you", "the", "and", "does", "not", "touch", "with", "sound", "make",
          "little", "like", "goes", "voice"}


def tidy(reply):
    # the model sometimes rambles; keep the first two sentences
    sentences = re.findall(r"[^.!?]+[.!?]*", reply.strip())
    return " ".join(s.strip() for s in sentences[:2])


def mentions(text, word):
    return re.search(rf"\b{re.escape(word.lower())}\b", text.lower()) is not None


def checked(reply, report):
    # 1B models sometimes praise a miss ("You're right!"), scold a hit, or flip a tip
    # ("touch the top" for R). Returns the reply to show, or None to use the built-in one.
    if not reply:
        return None
    text = reply.lower().replace("tongue twister", "")
    if "Correct: yes" in report:
        word = re.search(r"(?:Word to say|Tongue twister): (\w+)", report).group(1)
        ok = not RETRY.search(text) and ("Tongue twister" in report or mentions(text, word))
        return reply if ok else None
    if PRAISE.search(text):
        return None
    # the reply must pass on the mouth move for the target sound (first half of the tip)...
    how = report.split("Tip: ", 1)[-1].split(". ")[0].split(":", 1)[-1].lower()
    cues = {w[:5] for w in re.findall(r"[a-z]+", how) if len(w) > 3 and w not in FILLER}
    if cues and not any(re.search(rf"\b{c}", text) for c in cues):
        return None
    # ...without dropping a "not" ("does not touch the top" -> "touch the top")
    if re.search(r"\bnot\b", how) and not re.search(r"\b(not|no|off)\b|n't", text):
        return None
    # the code makes sure the child hears which word needs fixing / what it sounded like
    word = re.search(r"Missed word: (\w+)", report)
    heard = re.search(r"sounded like: (\w+)", report)
    if word and not mentions(text, word.group(1)):
        return f"Listen to {word.group(1)}. {reply}"
    if heard and not word and not mentions(text, heard.group(1)):
        return f"I heard {heard.group(1)}. {reply}"
    return reply


class PronunciationApp:
    def __init__(self, root):
        self.root = root
        self.index = 0
        self.total_stars = 0
        self.stt = None
        self.stream = None
        self.frames = []
        self.active = None          # (kind, mic button) while recording
        self.attempt = 0            # bumps on each try so late AI replies are ignored
        self.result_color = "black"  # green/red for the coach's reply to the last try
        self.events = queue.Queue()  # worker threads -> UI thread

        root.title("Say It! – Pronunciation Practice")
        root.geometry("760x640")
        root.configure(bg=BG)

        top = tk.Frame(root, bg=BG)
        top.pack(fill=tk.X, padx=16, pady=(12, 0))
        self.prev_btn = self.button(top, "◀", self.prev_pair, width=3)
        self.prev_btn.pack(side=tk.LEFT)
        self.focus_lbl = tk.Label(top, font=(FONT, 18, "bold"), bg=BG)
        self.focus_lbl.pack(side=tk.LEFT, padx=12)
        self.next_btn = self.button(top, "▶", self.next_pair, width=3)
        self.next_btn.pack(side=tk.LEFT)
        self.score_lbl = tk.Label(top, font=(FONT, 18, "bold"), fg=GOLD, bg=BG)
        self.score_lbl.pack(side=tk.RIGHT)

        # word cards
        cards = tk.Frame(root, bg=BG)
        cards.pack(fill=tk.X, padx=16, pady=12)
        self.word_lbls, self.word_mics = [], []
        self.cards = {}
        for side in ("wordA", "wordB"):
            card = tk.Frame(cards, bg="white", highlightbackground=BORDER,
                            highlightthickness=2)
            self.cards[side] = card
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6)
            lbl = tk.Label(card, font=(FONT, 40, "bold"), bg="white")
            lbl.pack(pady=(12, 4))
            row = tk.Frame(card, bg="white")
            row.pack(pady=(0, 12))
            self.button(row, "🔊 Listen", lambda s=side: self.listen(self.pair[s])).pack(side=tk.LEFT, padx=4)
            mic = self.button(row, "🎤 Say it", None)
            mic.config(command=lambda s=side, m=mic: self.toggle_recording(s, m))
            mic.pack(side=tk.LEFT, padx=4)
            self.word_lbls.append(lbl)
            self.word_mics.append(mic)

        # tongue twister card
        tw = tk.Frame(root, bg="white", highlightbackground=BORDER, highlightthickness=2)
        tw.pack(fill=tk.X, padx=22, pady=4)
        self.cards["twister"] = tw
        tk.Label(tw, text="Tongue Twister", font=(FONT, 11, "bold"), fg="#888",
                 bg="white").pack(anchor=tk.W, padx=12, pady=(8, 0))
        self.twister_txt = tk.Text(tw, height=2, wrap=tk.WORD, font=(FONT, 20, "bold"),
                                   bd=0, bg="white", padx=12, cursor="arrow")
        self.twister_txt.tag_config("hit", foreground=GREEN)
        self.twister_txt.tag_config("miss", foreground=RED, underline=True)
        self.twister_txt.pack(fill=tk.X)
        self.note_en = tk.Label(tw, font=(FONT, 11), fg="#555", bg="white",
                                wraplength=680, justify=tk.LEFT)
        self.note_en.pack(anchor=tk.W, padx=12)
        self.note_ja = tk.Label(tw, font=("Yu Gothic UI", 11), fg="#555", bg="white",
                                wraplength=680, justify=tk.LEFT)
        self.note_ja.pack(anchor=tk.W, padx=12)
        row = tk.Frame(tw, bg="white")
        row.pack(pady=10)
        self.button(row, "🔊 Listen",
                    lambda: self.listen(self.pair["tongueTwister"]["text"])).pack(side=tk.LEFT, padx=4)
        self.twister_mic = self.button(row, "🎤 Say it", None)
        self.twister_mic.config(command=lambda: self.toggle_recording("twister", self.twister_mic))
        self.twister_mic.pack(side=tk.LEFT, padx=4)

        # result
        self.stars_lbl = tk.Label(root, font=(FONT, 40), fg=GOLD, bg=BG)
        self.stars_lbl.pack(pady=(8, 0))
        self.feedback_lbl = tk.Label(root, font=(FONT, 14), bg=BG, wraplength=700)
        self.feedback_lbl.pack()

        self.mics = self.word_mics + [self.twister_mic]
        self.show_pair()
        self.set_mics(tk.DISABLED)
        self.feedback("Getting ready... (loading speech model)")
        threading.Thread(target=self.load_stt, daemon=True).start()
        root.after(50, self.process_events)

    @property
    def pair(self):
        return PAIRS[self.index]

    def button(self, parent, text, command, width=None):
        return tk.Button(parent, text=text, command=command, width=width,
                         font=(FONT, 13, "bold"), bg="#ffd966", activebackground="#ffcc33",
                         relief=tk.FLAT, padx=10, pady=4, cursor="hand2")

    # ---------- background work ----------

    def load_stt(self):
        # runs on CPU, downloads on first use
        self.stt = WhisperModel("base.en", device="cpu", compute_type="int8")
        self.events.put(("ready", None))

    def transcribe(self, kind, audio):
        pair = self.pair
        # For single words, hint both words equally so Whisper doesn't guess
        # some unrelated word, without favouring the right answer.
        prompt = f"{pair['wordA']}. {pair['wordB']}." if kind != "twister" else None
        segments, _ = self.stt.transcribe(audio, language="en", initial_prompt=prompt)
        heard = " ".join(s.text.strip() for s in segments).strip()
        self.events.put(("heard", (kind, heard)))

    def ask_coach(self, attempt, report, fallback):
        messages = [{"role": "system", "content": COACH_PROMPT}]
        for example, answer in COACH_EXAMPLES:
            messages += [{"role": "user", "content": example},
                         {"role": "assistant", "content": answer}]
        messages.append({"role": "user", "content": report})
        try:
            # not streamed: the reply is checked before the child sees it
            reply = tidy(ollama.chat(model=MODEL, messages=messages,
                                     options={"temperature": 0.4, "num_predict": 70})
                         ["message"]["content"])
        except Exception:
            reply = ""  # Ollama not running or model missing
        self.events.put(("coach", (attempt, checked(reply, report) or fallback)))

    def listen(self, text):
        threading.Thread(target=speak, args=(text,), daemon=True).start()

    # ---------- UI thread ----------

    def process_events(self):
        while not self.events.empty():
            kind, data = self.events.get()
            if kind == "ready":
                self.set_mics(tk.NORMAL)
                self.feedback("Press 🎤 Say it, speak, then press ⏹ Done.")
            elif kind == "heard":
                self.grade(*data)
                self.set_mics(tk.NORMAL)
            elif kind == "coach":
                attempt, text = data
                if attempt == self.attempt:
                    self.feedback(text.strip(), self.result_color)
        self.root.after(50, self.process_events)

    def toggle_recording(self, kind, mic):
        if self.active is None:
            self.attempt += 1
            self.frames = []
            self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                         callback=lambda data, *_: self.frames.append(data.copy()))
            self.stream.start()
            self.active = (kind, mic)
            self.set_mics(tk.DISABLED)
            mic.config(state=tk.NORMAL, text="⏹ Done", bg=RED, fg="white")
            self.prev_btn.config(state=tk.DISABLED)
            self.next_btn.config(state=tk.DISABLED)
            self.clear_result()
            self.feedback("Listening... 👂")
            return

        self.stream.stop()
        self.stream.close()
        self.active = None
        mic.config(text="🎤 Say it", bg="#ffd966", fg="black")
        self.prev_btn.config(state=tk.NORMAL)
        self.next_btn.config(state=tk.NORMAL)
        self.set_mics(tk.DISABLED)

        audio = np.squeeze(np.concatenate(self.frames)) if self.frames else np.zeros(1)
        if np.abs(audio).max() < SILENCE_LEVEL:
            self.feedback("I didn't hear anything. Speak a little louder!")
            self.set_mics(tk.NORMAL)
            return
        self.feedback("Checking... 🤔")
        threading.Thread(target=self.transcribe, args=(kind, audio), daemon=True).start()

    def grade(self, kind, heard):
        if not heard:
            self.feedback("I didn't catch that. Try again!")
            return
        if kind == "twister":
            stars, _, hits = check_twister(heard, self.pair["tongueTwister"]["text"])
            self.show_twister(hits)
        else:
            other = "wordB" if kind == "wordA" else "wordA"
            stars, _ = check_word(heard, self.pair[kind], self.pair[other])
        self.total_stars += stars
        self.show_result(kind, stars)
        self.score_lbl.config(text=f"★ {self.total_stars}")
        self.feedback("Coach is thinking... 💭", self.result_color)
        report, fallback = coach_message(self.pair, kind, heard, stars)
        threading.Thread(target=self.ask_coach, args=(self.attempt, report, fallback),
                         daemon=True).start()

    def show_pair(self):
        self.attempt += 1
        pair = self.pair
        self.focus_lbl.config(text=f"{pair['soundFocus']}   {self.index + 1} / {len(PAIRS)}")
        self.score_lbl.config(text=f"★ {self.total_stars}")
        self.word_lbls[0].config(text=pair["wordA"])
        self.word_lbls[1].config(text=pair["wordB"])
        self.note_en.config(text="💡 " + pair["tongueTwister"]["note"]["en"])
        self.note_ja.config(text="　 " + pair["tongueTwister"]["note"]["ja"])
        self.show_twister()
        self.clear_result()
        self.feedback("Press 🎤 Say it, speak, then press ⏹ Done." if self.stt else "")

    def show_result(self, kind, stars):
        # 2+ stars counts as correct: a perfect word, or a twister with one slip at most
        color = GREEN if stars >= 2 else RED
        self.result_color = color
        self.cards[kind].config(highlightbackground=color, highlightthickness=4)
        if kind != "twister":
            self.word_lbls[0 if kind == "wordA" else 1].config(fg=color)
        self.stars_lbl.config(text="★" * stars + "☆" * (3 - stars), fg=color)

    def clear_result(self):
        self.result_color = "black"
        for card in self.cards.values():
            card.config(highlightbackground=BORDER, highlightthickness=2)
        for lbl in self.word_lbls:
            lbl.config(fg="black")
        self.stars_lbl.config(text="", fg=GOLD)

    def show_twister(self, hits=None):
        # hits = indexes of words that were heard; colour words green/red
        self.twister_txt.config(state=tk.NORMAL)
        self.twister_txt.delete("1.0", tk.END)
        i = 0
        for token in self.pair["tongueTwister"]["text"].split():
            tag = None
            if clean(token):
                if hits is not None:
                    tag = "hit" if i in hits else "miss"
                i += 1
            self.twister_txt.insert(tk.END, token, tag)
            self.twister_txt.insert(tk.END, " ")
        self.twister_txt.config(state=tk.DISABLED)

    def prev_pair(self):
        self.index = (self.index - 1) % len(PAIRS)
        self.show_pair()

    def next_pair(self):
        self.index = (self.index + 1) % len(PAIRS)
        self.show_pair()

    def set_mics(self, state):
        for mic in self.mics:
            mic.config(state=state)

    def feedback(self, text, color="black"):
        self.feedback_lbl.config(text=text, fg=color)


if __name__ == "__main__":
    root = tk.Tk()
    PronunciationApp(root)
    root.mainloop()
