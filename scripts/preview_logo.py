#!/usr/bin/env python3
"""Preview SoftWiki logo in patorjk Coder Mini font + opencode color.
Run: python scripts/preview_logo.py
"""

# ── Coder Mini (patorjk.com) ─────────────────────────────────────────────────
CODER_MINI = [
    "             ▄▄                                           ",
    "             ██   ██           ▀▀  ▄▄     ▀▀    ",
    "▄█▀▀▀ ▄███▄ ▀██▀ ▀██▀▀ ██   ██ ██  ██ ▄█▀ ██    ",
    "▀███▄ ██ ██  ██   ██   ██ █ ██ ██  ████   ██    ",
    "▄▄▄█▀ ▀███▀  ██   ██    ██▀██  ██▄ ██ ▀█▄ ██▄",
]

def preview_coder_mini():
    for color_code, label in [
        ('\033[38;5;141m\033[1m', 'purple (opencode default)'),
        ('\033[38;5;111m\033[1m', 'blue'),
        ('\033[38;5;87m\033[1m',  'cyan'),
    ]:
        print(f"\n  ── Coder Mini — {label} ──")
        for line in CODER_MINI:
            print(color_code + "  " + line + '\033[0m')

print("\n" + "═"*62)
print("  SoftWiki — Coder Mini font (patorjk.com)")
print("═"*62)
preview_coder_mini()
print()


P  = '\033[38;5;141m\033[1m'   # purple bold (opencode default)
P2 = '\033[38;5;111m\033[1m'   # blue variant
P3 = '\033[38;5;213m\033[1m'   # pink variant
R  = '\033[0m'

# Each letter: (row1, row2, row3) — 4 chars wide
# Same character set as opencode: █ ▀ ▄ _ ^ ~

LETTERS_V1 = {
    # Variant 1 — closer to opencode style
    'S': ("▀▀▀█", "█▀▀▀", "▀▀▀▀"),   # top-right / mid-left / bottom bar
    'O': ("█▀▀█", "█__█", "▀▀▀▀"),   # same as opencode O
    'F': ("█▀▀▀", "██▀_", "▀   "),   # C + mid crossbar
    'T': ("████", "_██_", "_▀▀_"),   # full top bar / center post
    'W': ("█__█", "█▄▄█", "▀__▀"),   # two posts / V-connector
    'I': ("▀██▀", "_██_", "▀██▀"),   # I-beam
    'K': ("█__▄", "█▀█_", "▀__▀"),   # left post / diagonal
}

LETTERS_V2 = {
    # Variant 2 — S redesigned, T narrower
    'S': ("▄▀▀▀", "▀▀▀▄", "▄▄▄▀"),   # S curve
    'O': ("█▀▀█", "█__█", "▀▀▀▀"),
    'F': ("█▀▀▀", "█▀▀_", "▀   "),   # F with shorter mid bar
    'T': ("▀▀█▀", "__█_", "__▀_"),   # narrower T (like opencode N)
    'W': ("█__█", "█▄▄█", "▀__▀"),
    'I': ("▀██▀", "_██_", "▀██▀"),
    'K': ("█  ▄", "█▀█_", "▀  ▀"),   # K with more space
}

def render(letters, word_left, word_right, color, label):
    def row(word, i):
        return " ".join(letters[c][i] for c in word)

    pad, gap = "    ", "     "
    print(f"\n  ── {label} ──")
    for i in range(3):
        print(color + pad + row(word_left, i) + gap + row(word_right, i) + R)

print("\n" + "═"*60)
print("  SoftWiki Logo Preview")
print("═"*60)

render(LETTERS_V1, "SOFT", "WIKI", P,  "Variant 1 — purple (opencode default)")
render(LETTERS_V1, "SOFT", "WIKI", P2, "Variant 1 — blue")
render(LETTERS_V2, "SOFT", "WIKI", P,  "Variant 2 — S redesigned, narrower T")

print("\n  ── 单字对比 (V1 / V2) ──")
for c in "SOFTWIKI":
    v1 = LETTERS_V1[c]
    v2 = LETTERS_V2.get(c, v1)
    same = v1 == v2
    marker = "   " if same else " ← diff"
    print(f"  {c}  V1: {P}{v1[0]} {v1[1]} {v1[2]}{R}   V2: {P}{v2[0]} {v2[1]} {v2[2]}{R}{marker}")

print()
print("  opencode 原版参考:")
oc_left  = [("█▀▀█", "█__█", "▀▀▀▀"),  # o
             ("█▀▀█", "█__█", "█▀▀▀"),  # p
             ("█▀▀█", "█^^^", "▀▀▀▀"),  # e
             ("█▀▀▄", "█__█", "▀~~▀")]  # n
oc_right = [("█▀▀▀", "█___", "▀▀▀▀"),  # c
             ("█▀▀█", "█__█", "▀▀▀▀"),  # o
             ("█▀▀█", "█__█", "▀▀▀▀"),  # d
             ("█▀▀█", "█^^^", "▀▀▀▀")]  # e

pad, gap = "    ", "     "
for i in range(3):
    l = " ".join(l[i] for l in oc_left)
    r = " ".join(r[i] for r in oc_right)
    print('\033[38;5;75m\033[1m' + pad + l + gap + r + R)
print()
