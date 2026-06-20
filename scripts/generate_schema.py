#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_schema.py — Génère schema_neurosynapse.png (Sprint 7 v0.2)
Dépendances : matplotlib uniquement
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

BG = "#0d1117"
PANEL = "#161b22"
BORDER = "#30363d"
ACCENT = "#58a6ff"
GREEN = "#3fb950"
YELLOW = "#d29922"
RED = "#f85149"
ORANGE = "#e3b341"
TEXT = "#c9d1d9"
SUBTEXT = "#8b949e"
ACTIVE = "#1f6feb"
ABSENT = "#21262d"

fig, ax = plt.subplots(figsize=(20, 11))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 20)
ax.set_ylim(0, 11)
ax.axis("off")

# ── Helper ──────────────────────────────────────────────────────────────────

def box(x, y, w, h, color=PANEL, edge=BORDER, lw=1.2, radius=0.25):
    p = FancyBboxPatch((x, y), w, h,
                       boxstyle=f"round,pad=0,rounding_size={radius}",
                       facecolor=color, edgecolor=edge, linewidth=lw, zorder=3)
    ax.add_patch(p)

def label(x, y, txt, size=9, color=TEXT, ha="center", va="center",
          weight="normal", style="normal"):
    ax.text(x, y, txt, fontsize=size, color=color, ha=ha, va=va,
            fontweight=weight, fontstyle=style, zorder=5,
            fontfamily="monospace")

def arrow(x0, y0, x1, y1, color=ACCENT, lw=1.5):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle="-|>", color=color,
                                lw=lw, mutation_scale=12),
                zorder=4)

# ══════════════════════════════════════════════════════════════════════════════
# TITRE
# ══════════════════════════════════════════════════════════════════════════════
label(10, 10.55, "Pipeline NEUROSYNAPSE-ISR  ·  v0.2  ·  Sprint 7  ·  Score 82/100 GO",
      size=12, color=ACCENT, weight="bold")
label(10, 10.18, "IDEeS AP6-défi-13 · W7714-248676 · Scénario S-01 illustré",
      size=8.5, color=SUBTEXT)

# ══════════════════════════════════════════════════════════════════════════════
# ENTRÉES BRUTES (colonne gauche)
# ══════════════════════════════════════════════════════════════════════════════
inputs = [
    ("Radar RF", True,  "vecteur [256]"),
    ("EO / IR",  True,  "vecteur [256]"),
    ("SIGINT",   False, "vecteur 0 + flag=F"),
    ("Texte tac.",False, "vecteur 0 + flag=F"),
]
in_y = [8.55, 6.95, 5.35, 3.75]

for (name, active, note), iy in zip(inputs, in_y):
    col = ACTIVE if active else ABSENT
    ecol = ACCENT if active else BORDER
    box(0.3, iy - 0.45, 2.4, 0.9, color=col, edge=ecol, lw=1.5 if active else 1.0)
    label(1.5, iy + 0.08, name, size=9, color=TEXT if active else SUBTEXT, weight="bold")
    label(1.5, iy - 0.22, note, size=7.5, color=SUBTEXT if not active else "#79c0ff")
    status = "ACTIVE" if active else "ABSENTE"
    scol = GREEN if active else SUBTEXT
    label(1.5, iy - 0.6, f"── {status} ──", size=7, color=scol)

# Entrées label
label(1.5, 9.5, "Flux d'entrée", size=8.5, color=SUBTEXT, weight="bold")

# Phase 2 note (LAC-04/05)
box(0.3, 2.55, 2.4, 0.8, color="#0d2a1a", edge="#238636", lw=1.0)
label(1.5, 3.0, "Phase 2 (hors Phase 1)", size=7.5, color="#3fb950", weight="bold")
label(1.5, 2.75, "audio tactique · sonar", size=7, color="#3fb950", style="italic")

# ══════════════════════════════════════════════════════════════════════════════
# E1 — ENCODEURS MODAUX
# ══════════════════════════════════════════════════════════════════════════════
e1_y = [8.55, 6.95, 5.35, 3.75]
for iy, (name, active, _) in zip(e1_y, inputs):
    col = "#1a2744" if active else ABSENT
    ecol = "#388bfd" if active else BORDER
    box(3.1, iy - 0.45, 2.1, 0.9, color=col, edge=ecol)
    arch = "MobileNet" if name in ("Radar RF", "EO / IR") else "Transformer"
    label(4.15, iy + 0.1, arch, size=8, color=TEXT if active else SUBTEXT, weight="bold")
    label(4.15, iy - 0.2, "dim=256", size=7.5, color="#79c0ff" if active else SUBTEXT)
    if not active:
        label(4.15, iy - 0.42, "⊘ zéro", size=7, color=SUBTEXT)

# Bracket E1
box(3.0, 2.8, 2.3, 6.3, color="none", edge=ACCENT, lw=1.0, radius=0.15)
label(4.15, 9.45, "E1 — Encodeurs modaux", size=8.5, color=ACCENT, weight="bold")

# Arrows input → E1
for iy in e1_y:
    arrow(2.72, iy, 3.1, iy)

# ══════════════════════════════════════════════════════════════════════════════
# E2 — FUSION LATENTE
# ══════════════════════════════════════════════════════════════════════════════
box(5.6, 5.1, 2.3, 2.1, color="#1a1f2e", edge=ACCENT, lw=1.5)
label(6.75, 6.55, "E2", size=8, color=ACCENT, weight="bold")
label(6.75, 6.25, "Fusion latente", size=8.5, color=TEXT, weight="bold")
label(6.75, 5.95, "MLP · 2 couches · ReLU", size=7.5, color=SUBTEXT)
label(6.75, 5.67, "concat [256×4] → dim=128", size=7.5, color="#79c0ff")
label(6.75, 5.4, "vecteur fusion [128]", size=7.5, color=SUBTEXT)

# Arrows E1 → E2 (from 4 encoders to E2)
for iy in e1_y:
    arrow(5.2, iy, 5.6, 6.1 + (iy - 6.15) * 0.15)

# ══════════════════════════════════════════════════════════════════════════════
# E3 — PRÉDICATS NEURONAUX
# ══════════════════════════════════════════════════════════════════════════════
box(8.2, 4.4, 2.7, 3.4, color="#1a1f2e", edge="#8957e5", lw=1.5)
label(9.55, 7.55, "E3", size=8, color="#8957e5", weight="bold")
label(9.55, 7.25, "Prédicats neuronaux", size=8.5, color=TEXT, weight="bold")
label(9.55, 6.95, "MC Dropout N=30", size=7.5, color=SUBTEXT)

predicats = [
    ("mobile",            0.80, GREEN),
    ("signature_mil.",    0.70, YELLOW),
    ("en_zone_interdit.", 1.00, RED),
    ("arme",              0.00, SUBTEXT),
]
for i, (pname, pval, pcol) in enumerate(predicats):
    py = 6.55 - i * 0.55
    label(9.0, py, f"{pname}", size=7.5, color=pcol, ha="left")
    label(10.7, py, f"= {pval:.2f}", size=7.5, color=pcol, ha="right")

label(9.55, 4.65, "ECE < 0.05 (cible)", size=7, color=SUBTEXT, style="italic")

arrow(7.9, 6.15, 8.2, 6.15)

# ══════════════════════════════════════════════════════════════════════════════
# E4 — MOTEUR ROE ŁUKASIEWICZ
# ══════════════════════════════════════════════════════════════════════════════
box(11.2, 4.4, 2.8, 3.4, color="#1a1f2e", edge=YELLOW, lw=1.5)
label(12.6, 7.55, "E4", size=8, color=YELLOW, weight="bold")
label(12.6, 7.25, "Moteur ROE", size=8.5, color=TEXT, weight="bold")
label(12.6, 6.95, "Łukasiewicz différentiable", size=7.5, color=SUBTEXT)
label(12.6, 6.6, "Règle S-01 :", size=7.5, color=SUBTEXT)
label(12.6, 6.3, "mobile ∧ sig.mil.", size=7.5, color=YELLOW)
label(12.6, 6.05, "    ∧ zone_interdit.", size=7.5, color=YELLOW)
label(12.6, 5.7, "étape 1: max(0, 0.80+0.70-1)", size=7, color=SUBTEXT)
label(12.6, 5.45, "       = 0.50", size=7, color=TEXT)
label(12.6, 5.2, "étape 2: max(0, 0.50+1.00-1)", size=7, color=SUBTEXT)
label(12.6, 4.95, "       = 0.50  →  JAUNE", size=7, color=YELLOW, weight="bold")
label(12.6, 4.65, "score_alerte = 0.50", size=7.5, color="#d29922", weight="bold")

arrow(10.9, 6.15, 11.2, 6.15)

# ══════════════════════════════════════════════════════════════════════════════
# E5 — AUDIT & TRAÇABILITÉ
# ══════════════════════════════════════════════════════════════════════════════
box(14.25, 4.4, 2.95, 3.4, color="#1a1f2e", edge=GREEN, lw=1.5)
label(15.72, 7.55, "E5", size=8, color=GREEN, weight="bold")
label(15.72, 7.25, "Audit & Traçabilité", size=8.5, color=TEXT, weight="bold")
label(15.72, 6.95, "SHA-256 (NIST FIPS 180-4)", size=7.5, color=SUBTEXT)
label(15.72, 6.6, "Log NDJSON horodaté chaîné", size=7.5, color=SUBTEXT)
label(15.72, 6.3, "Graphe de connaissances", size=7.5, color=SUBTEXT)
label(15.72, 6.05, "(instancié par décision)", size=7, color=SUBTEXT, style="italic")
# Limite L2 annotation (LAC-01)
box(14.35, 5.35, 2.75, 0.55, color="#0d2a1a", edge="#238636", lw=0.8)
label(15.72, 5.67, "Limite L2 : ±5 min", size=7.5, color="#3fb950", weight="bold")
label(15.72, 5.42, "extension post-NMT-5", size=7, color="#3fb950", style="italic")
label(15.72, 4.65, "suivi cross-sessions : hors Phase 1", size=7, color=SUBTEXT, style="italic")

arrow(14.0, 6.15, 14.25, 6.15)

# ══════════════════════════════════════════════════════════════════════════════
# SORTIE DÉCISION
# ══════════════════════════════════════════════════════════════════════════════
box(17.45, 5.35, 2.25, 2.4, color="#1c2200", edge=YELLOW, lw=2.0)
label(18.57, 7.45, "DÉCISION", size=9, color=TEXT, weight="bold")
label(18.57, 7.1, "niveau_alerte", size=8, color=SUBTEXT)

# Niveaux
niveaux = [("ROUGE", RED), ("ORANGE", ORANGE), ("JAUNE →", YELLOW), ("VERT", GREEN)]
for i, (nv, nc) in enumerate(niveaux):
    ny = 6.7 - i * 0.45
    weight = "bold" if "JAUNE" in nv else "normal"
    label(18.57, ny, nv, size=8.5, color=nc, weight=weight)

label(18.57, 5.5, "ALERTER  ◀  S-01", size=8, color=YELLOW, weight="bold")

arrow(17.2, 6.15, 17.45, 6.15)

# ══════════════════════════════════════════════════════════════════════════════
# SHA-256 HASH DISPLAY
# ══════════════════════════════════════════════════════════════════════════════
box(5.6, 3.7, 11.85, 0.65, color="#0d1a0d", edge=GREEN, lw=0.8)
label(11.52, 4.07, "SHA-256 (S-01 Sprint 7) :", size=7.5, color=SUBTEXT, ha="left",
      va="center")
label(11.52, 3.87, "f841dcba1f79b4319be991776c06a50655cf7eb4de54b9f15fe299acfa548785",
      size=6.8, color=GREEN, ha="left", va="center")

# ══════════════════════════════════════════════════════════════════════════════
# LÉGENDE & ANNOTATIONS
# ══════════════════════════════════════════════════════════════════════════════
box(0.3, 0.25, 8.0, 1.05, color=PANEL, edge=BORDER, lw=0.8)
label(0.7, 1.05, "Légende :", size=8, color=SUBTEXT, ha="left")
items = [
    (ACTIVE,   "Modalité active"),
    (ABSENT,   "Modalité absente (vecteur zéro)"),
    ("#0d2a1a","Phase 2 / Extension future"),
    (GREEN,    "Critère éliminatoire SATISFAIT"),
]
for i, (c, t) in enumerate(items):
    lx = 0.7 + i * 2.0
    ax.add_patch(mpatches.Rectangle((lx, 0.35), 0.25, 0.35,
                                    facecolor=c, edgecolor=BORDER, linewidth=0.5, zorder=5))
    label(lx + 0.35, 0.52, t, size=7, color=SUBTEXT, ha="left")

box(8.5, 0.25, 11.2, 1.05, color=PANEL, edge=BORDER, lw=0.8)
label(8.8, 1.05, "Invariants Sprint 7 :", size=8, color=SUBTEXT, ha="left")
inv_items = [
    "score_alerte = 0.50 ✓",
    "niveau_alerte = JAUNE ✓",
    "≥ 2 modalités actives ✓",
    "SWaP < 220 Ko / ≤ 50 ms (Jetson Orin NX) — validation J-N4/N5",
    "limites_declarees = [L1, L2, L4]  ·  GLOSSAIRE.md v1.0",
]
for i, t in enumerate(inv_items):
    col = GREEN if "✓" in t else SUBTEXT
    label(8.8, 0.85 - i * 0.14, t, size=7, color=col, ha="left")

# Footer
label(10, 0.08, "NEUROSYNAPSE-ISR · IDEeS AP6-défi-13 · Sprint 7 · 2026-05-25 · GLOSSAIRE.md v1.0 · NMT-4 → NMT-5",
      size=7, color=SUBTEXT)

# ══════════════════════════════════════════════════════════════════════════════
# SAUVEGARDE
# ══════════════════════════════════════════════════════════════════════════════
import os
out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "schema_neurosynapse.png")
plt.tight_layout(pad=0)
plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
print(f"Schéma écrit : {os.path.abspath(out)}")
