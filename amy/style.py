"""Plot style for Amy's EDA, carried over from the Allston energy & ICT project (src/allston.py).

- Type: Suisse Intl if installed (Amy's licensed font), otherwise Arial / Helvetica / DejaVu Sans.
  Graphic title 18 SemiBold, subtitle 11 grey, labels and legend 10, source line 9. Nothing below 9 pt.
- Lines: thicker = more important. profile 2 pt (baseline), heavy 1.5 (the emphasised series),
  medium 1, light 0.5 (spines), hairline 0.25 (gridlines, long-dashed because they don't physically exist).
- One color = one meaning. Do not reassign.
"""
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

FONT_FAMILY = "Suisse Intl"
FONT_DIR = Path.home() / "Library" / "Fonts"
TYPE = {"graphic_title": 18, "caption": 11, "label": 10, "legend": 10, "source": 9}
LINE_PT = {"profile": 2.0, "heavy": 1.5, "medium": 1.0, "light": 0.5, "hairline": 0.25}
DASH = {"solid": "solid", "dashed": (0, (4, 2)), "longdash": (0, (9, 3)), "dotted": (0, (1, 1.6))}
PANEL = {"S": (5.5, 4), "L": (8, 5.5), "W": (11, 4.5)}   # S/L from the Allston project; W = wide two-panel

# ---- colors (Allston palette, mapped to this project)
NAVY = "#1F3A5F"         # Allston "electric" navy: the single accent for one-series charts
TERRACOTTA = "#C8553D"   # Allston terracotta: second accent / highlight
# Stack order (bottom -> top) is chosen so similar tints are never adjacent. Validated: adjacent-pair
# colorblind dE >= 12.6. Three light tints are under 3:1 contrast on white, so fuel charts carry direct labels.
FUEL_COLOR = {"nuclear": "#9DB0C8", "coal": "#444444", "gas": "#E0A458",   # gas keeps its Allston meaning
              "wind": "#3E7CB1", "solar": "#E8A898", "other": "#8A8A8A"}   # other = hydro + oil + other
NEUTRAL = {"ink": "#222222", "secondary": "#555555", "grid": "#BBBBBB", "shade": "#EFEFEF"}
# one-hue sequential ramp (light -> dark navy) for magnitude
SEQ = LinearSegmentedColormap.from_list("navy", ["#F4F4F2", NAVY])


def set_style():
    mpl.rcdefaults()   # clear any seaborn theme set earlier in the notebook
    for f in FONT_DIR.glob("SuisseIntl-*.otf"):
        try:
            mpl.font_manager.fontManager.addfont(str(f))
        except Exception:
            pass
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": [FONT_FAMILY, "Arial", "Helvetica Neue", "DejaVu Sans"],
        "font.size": TYPE["label"], "axes.labelsize": TYPE["label"],
        "xtick.labelsize": TYPE["label"], "ytick.labelsize": TYPE["label"],
        "axes.titlesize": 12, "axes.titleweight": "semibold", "axes.titlelocation": "left",
        "legend.fontsize": TYPE["legend"], "legend.frameon": False,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#444444", "axes.linewidth": LINE_PT["light"],
        "xtick.major.width": LINE_PT["light"], "ytick.major.width": LINE_PT["light"],
        "lines.linewidth": LINE_PT["heavy"], "axes.grid": False,
        "figure.facecolor": "white", "savefig.facecolor": "white", "figure.dpi": 100,
        "figure.constrained_layout.use": True,
    })


def chart_lines(ax, grid=True):
    """2 pt baseline, 0.5 pt left spine, long-dash hairline gridlines behind the data."""
    ax.spines["bottom"].set_linewidth(LINE_PT["profile"])
    ax.spines["bottom"].set_color(NEUTRAL["ink"])
    ax.spines["left"].set_linewidth(LINE_PT["light"])
    if grid:
        ax.grid(axis="y", color=NEUTRAL["grid"], linewidth=LINE_PT["hairline"] * 2, linestyle=DASH["longdash"])
        ax.set_axisbelow(True)


def frame(fig, title, subtitle, source="Source: EIA-930 Hourly Electric Grid Monitor, six-month bulk files."):
    """Every chart: title, grey subtitle (what · where · when), and a source line."""
    h = fig.get_figheight()
    fig.text(0.01, 1 - 0.12 / h, title, fontsize=TYPE["graphic_title"], fontweight="semibold", va="top")
    fig.text(0.01, 1 - 0.50 / h, subtitle, fontsize=TYPE["caption"], color=NEUTRAL["secondary"], va="top")
    fig.text(0.01, 0.08 / h, source, fontsize=TYPE["source"], color=NEUTRAL["secondary"], va="bottom")
    fig.get_layout_engine().set(rect=(0, 0.35 / h, 1, 1 - 1.15 / h))


def save(fig, path):
    fig.savefig(path, dpi=300)
    plt.show()
