import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO

from io import BytesIO
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from io import BytesIO
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def fig_to_png_response(dpi: int = 180):
    """
    Backward-compatible helper: save the CURRENT pyplot figure to PNG BytesIO.
    (Used by older routes that rely on global plt state.)
    """
    buf = BytesIO()
    plt.savefig(
        buf,
        format="png",
        dpi=dpi,
        bbox_inches="tight",
        facecolor="white",
        pad_inches=0.15
    )
    plt.close()  # close current figure to avoid memory leaks
    buf.seek(0)
    return buf


def fig_to_png(fig, dpi: int = 180):
    """
    Convert a matplotlib Figure to PNG BytesIO.
    Safe: saves the provided figure (no global plt).
    """
    buf = BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=dpi,
        bbox_inches="tight",
        facecolor="white",
        pad_inches=0.15
    )
    buf.seek(0)
    plt.close(fig)
    return buf



# -----------------------------
# Confusion Matrix plot
# -----------------------------
def plot_confusion_matrix_png(cm, labels, title="Confusion Matrix (Hybrid Model)"):
    fig, ax = plt.subplots(figsize=(6, 5), dpi=160)

    im = ax.imshow(cm, cmap="Blues")

    ax.set_xticks(np.arange(len(labels)))
    ax.set_yticks(np.arange(len(labels)))
    ax.set_xticklabels(labels)
    ax.set_yticklabels(labels)

    ax.set_xlabel("Predicted Label")
    ax.set_ylabel("Actual Label")
    ax.set_title(title)

    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(
                j, i, cm[i, j],
                ha="center", va="center",
                fontsize=11,
                color="black"
            )

    fig.colorbar(im, fraction=0.046, pad=0.04)

    return fig_to_png(fig)
