from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from numpy.typing import NDArray

from overlap_calculator.utils.logging import format_log

LOGGER = logging.getLogger(__name__)

_METHOD_COLORS: dict[str, str] = {
    "gaussian": "#0f766e",
    "lorentzian": "#db2777",
}
_LIGHT_COLOR = "#1d4ed8"
_TIFF_PIL_KWARGS: dict[str, object] = {"compression": "tiff_lzw"}


def _method_color(method: str, index: int = 0) -> str:
    fallback_palette = ["#0f766e", "#db2777", "#7c3aed", "#b45309"]
    return _METHOD_COLORS.get(method, fallback_palette[index % len(fallback_palette)])


def _normalize_max(values: NDArray[np.float64]) -> NDArray[np.float64]:
    max_value = float(np.max(values)) if values.size else 0.0
    if max_value <= 0.0:
        return np.zeros_like(values)
    return values / max_value


def _finalize_with_legend_below(
    fig: Figure,
    ax: Axes,
    entries: int,
    out_path: Path,
    dpi: int,
    extra_handles: tuple[Sequence[Artist], Sequence[str]] | None = None,
) -> None:
    total = max(1, entries + (len(extra_handles[0]) if extra_handles else 0))
    if total > 16:
        ncol = 4
    elif total > 8:
        ncol = 3
    elif total > 2:
        ncol = 2
    else:
        ncol = total
    rows = int(np.ceil(total / ncol))
    handles, labels = ax.get_legend_handles_labels()
    if extra_handles is not None:
        handles = list(handles) + list(extra_handles[0])
        labels = list(labels) + list(extra_handles[1])
    bottom_margin = 0.20 + (rows - 1) * 0.05
    anchor_y = -(0.18 + (rows - 1) * 0.05)
    ax.legend(
        handles,
        labels,
        frameon=False,
        fontsize=11,
        loc="upper center",
        bbox_to_anchor=(0.5, anchor_y),
        ncol=min(ncol, total),
        handlelength=2.0,
        columnspacing=1.2,
    )
    fig.subplots_adjust(bottom=bottom_margin, left=0.1, right=0.96, top=0.9)
    try:
        fig.savefig(
            out_path,
            dpi=dpi,
            format="tiff",
            bbox_inches="tight",
            pad_inches=0.04,
            pil_kwargs=_TIFF_PIL_KWARGS,
        )
    finally:
        plt.close(fig)


def plot_absorptance_absolute(
    method_curves: dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]],
    out_path: Path,
    dpi: int,
    title: str | None = None,
) -> None:
    LOGGER.info(format_log("plot", "absorptance_absolute", out_path=out_path))
    fig, ax = plt.subplots(figsize=(9, 6.5))
    for index, (method, (wavelengths, absorptance)) in enumerate(method_curves.items()):
        ax.plot(
            wavelengths,
            absorptance,
            linewidth=2.5,
            color=_method_color(method, index),
            label=method,
        )
    ax.set_xlabel("Wavelength (nm)", fontsize=14)
    ax.set_ylabel("Absorptance α(λ) (Beer-Lambert, [0, 1])", fontsize=13)
    ax.set_ylim(bottom=0.0)
    if title:
        ax.set_title(title, fontsize=15)
    ax.tick_params(axis="both", labelsize=11)
    _finalize_with_legend_below(fig, ax, entries=len(method_curves), out_path=out_path, dpi=dpi)


def plot_absorptance_normalized(
    method_curves: dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]],
    out_path: Path,
    dpi: int,
    title: str | None = None,
) -> None:
    LOGGER.info(format_log("plot", "absorptance_normalized", out_path=out_path))
    fig, ax = plt.subplots(figsize=(9, 6.5))
    for index, (method, (wavelengths, absorptance)) in enumerate(method_curves.items()):
        ax.plot(
            wavelengths,
            _normalize_max(absorptance),
            linewidth=2.5,
            color=_method_color(method, index),
            label=method,
        )
    ax.set_xlabel("Wavelength (nm)", fontsize=14)
    ax.set_ylabel("α(λ) / max(α)", fontsize=13)
    ax.set_ylim(0.0, 1.05)
    if title:
        ax.set_title(title, fontsize=15)
    ax.tick_params(axis="both", labelsize=11)
    _finalize_with_legend_below(fig, ax, entries=len(method_curves), out_path=out_path, dpi=dpi)


def plot_light_source_spectrum(
    wavelengths: NDArray[np.float64],
    intensity: NDArray[np.float64],
    out_path: Path,
    dpi: int,
    title: str | None = None,
) -> None:
    LOGGER.info(format_log("plot", "light_source", out_path=out_path))
    fig, ax = plt.subplots(figsize=(9, 6.5))
    ax.plot(wavelengths, intensity, linewidth=2.5, color=_LIGHT_COLOR, label="Intensity")
    ax.set_xlabel("Wavelength (nm)", fontsize=14)
    ax.set_ylabel("Intensity (native units)", fontsize=13)
    if title:
        ax.set_title(title, fontsize=15)
    ax.tick_params(axis="both", labelsize=11)
    _finalize_with_legend_below(fig, ax, entries=1, out_path=out_path, dpi=dpi)


def plot_overlap_absolute(
    method_absorptance: dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]],
    light_wavelengths: NDArray[np.float64],
    light_intensity: NDArray[np.float64],
    light_unit: str,
    out_path: Path,
    dpi: int,
    title: str | None = None,
) -> None:
    LOGGER.info(format_log("plot", "overlap_absolute", out_path=out_path))
    fig, ax_left = plt.subplots(figsize=(10, 7))
    ax_right = ax_left.twinx()

    light_line = ax_right.plot(
        light_wavelengths,
        light_intensity,
        linewidth=2.4,
        color=_LIGHT_COLOR,
        label="Light intensity",
    )
    ax_right.set_ylabel(f"Light intensity ({light_unit})", fontsize=13, color=_LIGHT_COLOR)
    ax_right.tick_params(axis="y", labelcolor=_LIGHT_COLOR, labelsize=11)
    ax_right.set_ylim(bottom=0.0)

    max_light = float(np.max(light_intensity)) if light_intensity.size else 0.0
    light_shape = light_intensity / max_light if max_light > 0.0 else light_intensity
    for index, (method, (wavelengths, absorptance)) in enumerate(method_absorptance.items()):
        color = _method_color(method, index)
        ax_left.plot(
            wavelengths,
            absorptance,
            linewidth=2.4,
            color=color,
            label=f"Absorptance ({method})",
        )
        intersection = np.minimum(absorptance, light_shape)
        ax_left.fill_between(
            wavelengths,
            0.0,
            intersection,
            color=color,
            alpha=0.25,
            label=f"Overlap area min(alpha, I_hat) ({method})",
        )
    ax_left.set_xlabel("Wavelength (nm)", fontsize=14)
    ax_left.set_ylabel("Absorptance α(λ) [0, 1]", fontsize=13)
    ax_left.set_ylim(0.0, 1.05)
    ax_left.tick_params(axis="both", labelsize=11)
    if title:
        ax_left.set_title(title, fontsize=15)

    _finalize_with_legend_below(
        fig,
        ax_left,
        entries=2 * len(method_absorptance),
        out_path=out_path,
        dpi=dpi,
        extra_handles=(light_line, ["Light intensity"]),
    )


def plot_overlap_normalized(
    method_absorptance: dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]],
    light_wavelengths: NDArray[np.float64],
    light_intensity: NDArray[np.float64],
    out_path: Path,
    dpi: int,
    title: str | None = None,
) -> None:
    LOGGER.info(format_log("plot", "overlap_normalized", out_path=out_path))
    fig, ax = plt.subplots(figsize=(10, 7))
    light_norm = _normalize_max(light_intensity)
    ax.plot(
        light_wavelengths,
        light_norm,
        linewidth=2.4,
        color=_LIGHT_COLOR,
        label="Light (normalized)",
    )
    for index, (method, (wavelengths, absorptance)) in enumerate(method_absorptance.items()):
        absorptance_norm = _normalize_max(absorptance)
        color = _method_color(method, index)
        ax.plot(
            wavelengths,
            absorptance_norm,
            linewidth=2.4,
            color=color,
            label=f"Absorptance ({method}, normalized)",
        )
        intersection = np.minimum(absorptance_norm, light_norm)
        ax.fill_between(
            wavelengths,
            0.0,
            intersection,
            color=color,
            alpha=0.28,
            label=f"Overlap area min(alpha_hat, I_hat) ({method})",
        )
    ax.set_xlabel("Wavelength (nm)", fontsize=14)
    ax.set_ylabel("Normalized magnitude", fontsize=13)
    ax.set_ylim(0.0, 1.05)
    if title:
        ax.set_title(title, fontsize=15)
    ax.tick_params(axis="both", labelsize=11)
    _finalize_with_legend_below(
        fig,
        ax,
        entries=1 + 2 * len(method_absorptance),
        out_path=out_path,
        dpi=dpi,
    )


def plot_ranking_bars(
    labels: Sequence[str],
    values: Sequence[float],
    out_path: Path,
    dpi: int,
    title: str,
    y_label: str,
    x_label: str,
    bar_color: str = "#0f766e",
) -> None:
    LOGGER.info(format_log("plot", "ranking_bars", out_path=out_path))
    n = len(labels)
    fig_width = max(8.0, 0.55 * n + 4.0)
    fig, ax = plt.subplots(figsize=(fig_width, 6.5))
    x_positions = np.arange(n)
    bars = ax.bar(
        x_positions,
        values,
        color=bar_color,
        edgecolor="#0b3b36",
        linewidth=0.8,
        zorder=3,
    )
    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=11)
    ax.set_xlabel(x_label, fontsize=13)
    ax.set_ylabel(y_label, fontsize=13)
    ax.set_title(title, fontsize=14)
    ax.tick_params(axis="y", labelsize=11)
    ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.5, zorder=0)

    finite_values = [float(v) for v in values if np.isfinite(v)]
    if finite_values:
        max_value = max(finite_values)
        min_value = min(finite_values)
        upper = max_value * 1.12 if max_value > 0.0 else 1.0
        lower = min(0.0, min_value * 1.05)
        ax.set_ylim(lower, upper)
        offset = (upper - lower) * 0.012
    else:
        ax.set_ylim(0.0, 1.0)
        offset = 0.012

    for bar, value in zip(bars, values, strict=False):
        if not np.isfinite(value):
            continue
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + offset,
            f"{value:.4f}",
            ha="center",
            va="bottom",
            fontsize=9,
            color="#111827",
        )

    fig.subplots_adjust(bottom=0.22, left=0.10, right=0.97, top=0.90)
    try:
        fig.savefig(
            out_path,
            dpi=dpi,
            format="tiff",
            bbox_inches="tight",
            pad_inches=0.04,
            pil_kwargs=_TIFF_PIL_KWARGS,
        )
    finally:
        plt.close(fig)


def plot_absorption_overlay(
    spectra: list[tuple[str, NDArray[np.float64], NDArray[np.float64]]],
    out_path: Path,
    dpi: int,
    title: str | None = None,
    y_label: str = "Absorptance α(λ)",
) -> None:
    LOGGER.info(format_log("plot", "absorption_overlay", out_path=out_path))
    fig, ax = plt.subplots(figsize=(11, 7))
    for sample_id, wavelengths, absorption in spectra:
        ax.plot(wavelengths, absorption, linewidth=2.0, label=sample_id)
    ax.set_xlabel("Wavelength (nm)", fontsize=14)
    ax.set_ylabel(y_label, fontsize=14)
    if title:
        ax.set_title(title, fontsize=16)
    ax.tick_params(axis="both", labelsize=12)
    _finalize_with_legend_below(fig, ax, entries=len(spectra), out_path=out_path, dpi=dpi)
