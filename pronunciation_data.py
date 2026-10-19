# Minimal pairs for pronunciation practice.
# Keys match the original TypeScript dataset, so new entries can be pasted in
# by quoting the keys.

PAIRS = [
    {
        "id": "right-light",
        "soundFocus": "R vs L",
        "tongueTwister": {
            "text": "Right by the light, read it right in the light.",
            "note": {
                "en": "Move slowly between R and L without adding an extra vowel.",
                "ja": "RとLをゆっくり切り替え、余計な母音を足さずに言います。",
            },
        },
        "wordA": "right",
        "wordB": "light",
    },
    {
        "id": "rice-lice",
        "soundFocus": "R vs L",
        "tongueTwister": {
            "text": "Rice on the left, lice on the right.",
            "note": {
                "en": "Keep rice and lice clearly separated at the first sound.",
                "ja": "語頭のRとLをはっきり分けて言います。",
            },
        },
        "wordA": "rice",
        "wordB": "lice",
    },
    {
        "id": "road-load",
        "soundFocus": "R vs L",
        "tongueTwister": {
            "text": "Roll down the road with a light load.",
            "note": {
                "en": "Practice R in roll and road, then L in light and load.",
                "ja": "roll / road のR、light / load のLを順番に切り替えます。",
            },
        },
        "wordA": "road",
        "wordB": "load",
    },
    {
        "id": "glass-grass",
        "soundFocus": "R vs L",
        "tongueTwister": {
            "text": "Green grass grows near a clear glass.",
            "note": {
                "en": "Listen for the cluster difference in grass and glass.",
                "ja": "grass と glass の子音連結の違いを意識します。",
            },
        },
        "wordA": "glass",
        "wordB": "grass",
    },
    {
        "id": "free-flee",
        "soundFocus": "R vs L",
        "tongueTwister": {
            "text": "Feel free to flee freely.",
            "note": {
                "en": "Switch between free and flee while keeping the vowel stable.",
                "ja": "母音を安定させたまま、free と flee を切り替えます。",
            },
        },
        "wordA": "free",
        "wordB": "flee",
    },
    {
        "id": "red-led",
        "soundFocus": "R vs L",
        "tongueTwister": {
            "text": "Red lights led Ray along the lane.",
            "note": {
                "en": "Alternate R and L across connected words.",
                "ja": "文の中でRとLを交互に切り替えます。",
            },
        },
        "wordA": "red",
        "wordB": "led",
    },
]

# Words that sound the same. Whisper writes a correct spelling of what it
# hears, so a perfect "lice" can come back as "lies". Each group is treated
# as one word when grading. Keep R and L sounds in separate groups.
SOUNDS_LIKE = [
    ["right", "write", "rite", "wright"],
    ["light", "lite"],
    ["rice"],
    ["lice", "lyse"],
    ["road", "rode", "rowed"],
    ["load", "lode", "lowed"],
    ["roll", "role"],
    ["red", "read"],
    ["led", "lead"],
    ["flee", "flea"],
    ["ray", "rae", "rey"],
    ["lane", "lain"],
]
