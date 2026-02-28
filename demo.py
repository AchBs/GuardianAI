#!/usr/bin/env python3
"""
demo.py
=======
Standalone Guardian AI demonstration script.

Runs the full pipeline and generates matplotlib charts + a printed report.
No web server required - useful for offline demos or notebooks.

Usage:
    python3 demo.py
    python3 demo.py --attack-prob 0.08 --seed 123
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from guardian_ai.simulator import TunisianCitySimulator
from guardian_ai.detector  import FDIDetector
from guardian_ai.optimizer import SmartCityOptimizer


# ── Colour palette (dark theme) ───────────────────────────────────────────────
BG_DARK  = "#050d1a"
BG_CARD  = "#0c1b2e"
C_RAW    = "#60a5fa"
C_CORR   = "#00d4ff"
C_OPT    = "#00e676"
C_ATK    = "#ff1744"
C_WATER  = "#a78bfa"
C_W_OPT  = "#7b2fff"
C_SAVE   = "#00e676"
C_TARGET = "#ffab00"
C_TEXT   = "#ccd6f6"
C_DIM    = "#8892b0"


def run_pipeline(attack_prob: float = 0.04, seed: int = 42) -> tuple:
    """Execute the full Guardian AI pipeline and return (df, metrics)."""
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║          GUARDIAN AI  ·  Tunisia Smart Cities         ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    print("[1/5] Generating clean baseline (48h reference) for detector training…")
    sim      = TunisianCitySimulator(seed=seed)
    clean_df = sim.generate_normal_data(hours=48)
    print(f"      → {len(clean_df)} clean reference points")

    print("[2/5] Generating 24h sensor data for Tunisian city…")
    df = sim.generate_normal_data(hours=24)
    print(f"      → {len(df)} data points generated (1-minute resolution)")

    print(f"[3/5] Injecting FDI attacks (p={attack_prob:.0%})…")
    df = sim.inject_fdi_attacks(df, attack_probability=attack_prob)
    n_attacks = int(df["is_attack"].sum())
    types = df[df["is_attack"]]["attack_type"].value_counts().to_dict()
    print(f"      → {n_attacks} attack points injected ({n_attacks/len(df):.1%}): {types}")

    print("[4/5] Training detector on clean baseline + running hybrid ensemble…")
    detector = FDIDetector()
    detector.fit(clean_df)            # fit on attack-free reference data
    df = detector.detect(df)
    df = detector.correct_data(df)
    metrics_det = detector.compute_detection_metrics(df)
    print(f"      → Precision: {metrics_det['precision']:.1%}  "
          f"Recall: {metrics_det['recall']:.1%}  "
          f"F1: {metrics_det['f1_score']:.1%}")

    print("[5/5] Optimising energy & water allocation…")
    optimizer = SmartCityOptimizer()
    df = optimizer.optimize(df)
    metrics = optimizer.compute_metrics(df)
    metrics.update(metrics_det)

    return df, metrics


def plot_results(df: pd.DataFrame, metrics: dict, save_path: str = "guardian_ai_report.png"):
    """Generate a comprehensive 5-panel diagnostic report."""
    plt.rcParams.update({
        "figure.facecolor":  BG_DARK,
        "axes.facecolor":    BG_CARD,
        "axes.edgecolor":    "#1d3a5c",
        "axes.labelcolor":   C_TEXT,
        "axes.titlecolor":   C_TEXT,
        "xtick.color":       C_DIM,
        "ytick.color":       C_DIM,
        "grid.color":        "#0d2040",
        "text.color":        C_TEXT,
        "legend.facecolor":  BG_CARD,
        "legend.edgecolor":  "#1d3a5c",
        "font.size":         9,
    })

    fig = plt.figure(figsize=(18, 13), facecolor=BG_DARK)
    fig.suptitle("Guardian AI — Tunisia Smart Cities  |  24-Hour Simulation Report",
                 fontsize=15, fontweight="bold", color=C_TEXT, y=0.98)

    gs  = GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.32,
                   left=0.06, right=0.97, top=0.93, bottom=0.06)

    minutes = np.arange(len(df))
    ts      = df["timestamp"].dt.strftime("%H:%M").values
    xticks  = np.arange(0, len(df), 60)   # every hour
    xlabels = ts[xticks]

    attack_idx   = df.index[df["is_attack"]].tolist()
    detected_idx = df.index[df["detected_attack"]].tolist()

    # ── Panel 1: Lighting raw vs corrected vs optimised ──────────────────
    ax1 = fig.add_subplot(gs[0, :2])
    ax1.set_title("⚡  Public Lighting — Raw / Corrected / Optimised (kW)")
    ax1.plot(minutes, df["lighting_kw"],         color=C_RAW,  alpha=0.55, lw=1.2, label="Raw (with attacks)")
    ax1.plot(minutes, df["lighting_corrected"],   color=C_CORR, alpha=0.85, lw=1.6, label="Corrected")
    ax1.plot(minutes, df["lighting_optimized"],   color=C_OPT,  alpha=0.95, lw=2.0, label="Optimised", ls="--")
    ax1.fill_between(minutes, df["lighting_kw"], df["lighting_optimized"],
                     alpha=0.07, color=C_OPT)

    # Shade attack regions
    for idx in attack_idx:
        ax1.axvline(idx, color=C_ATK, alpha=0.12, lw=1)
    if attack_idx:
        ax1.scatter(attack_idx, df.loc[attack_idx, "lighting_kw"],
                    color=C_ATK, s=12, zorder=5, label="FDI Attack", alpha=0.7)

    ax1.set_xticks(xticks); ax1.set_xticklabels(xlabels, rotation=45)
    ax1.set_ylabel("kW"); ax1.legend(fontsize=8, loc="upper right")
    ax1.grid(True, alpha=0.4)

    # ── Panel 2: Water raw vs corrected vs optimised ─────────────────────
    ax2 = fig.add_subplot(gs[1, :2])
    ax2.set_title("💧  Water Distribution — Raw / Corrected / Optimised (L/min)")
    ax2.plot(minutes, df["water_lpm"],       color=C_WATER, alpha=0.55, lw=1.2, label="Raw (with attacks)")
    ax2.plot(minutes, df["water_corrected"], color="#c084fc", alpha=0.85, lw=1.6, label="Corrected")
    ax2.plot(minutes, df["water_optimized"], color=C_W_OPT, alpha=0.95, lw=2.0, label="Optimised", ls="--")
    if attack_idx:
        ax2.scatter(attack_idx, df.loc[attack_idx, "water_lpm"],
                    color=C_ATK, s=12, zorder=5, label="FDI Attack", alpha=0.7)
    ax2.set_xticks(xticks); ax2.set_xticklabels(xlabels, rotation=45)
    ax2.set_ylabel("L/min"); ax2.legend(fontsize=8, loc="upper right")
    ax2.grid(True, alpha=0.4)

    # ── Panel 3: Energy savings % ─────────────────────────────────────────
    ax3 = fig.add_subplot(gs[2, :2])
    ax3.set_title("📊  Cumulative Energy Savings (%) — Target: 30%")
    ax3.fill_between(minutes, df["cumulative_savings_pct"],
                     alpha=0.25, color=C_SAVE)
    ax3.plot(minutes, df["cumulative_savings_pct"], color=C_SAVE, lw=2.0, label="Actual savings")
    ax3.axhline(30, color=C_TARGET, lw=1.5, ls="--", label="30% target")
    ax3.set_xticks(xticks); ax3.set_xticklabels(xlabels, rotation=45)
    ax3.set_ylabel("%"); ax3.set_ylim(0, 50)
    ax3.legend(fontsize=8, loc="lower right")
    ax3.grid(True, alpha=0.4)

    # ── Panel 4: Anomaly scores ───────────────────────────────────────────
    ax4 = fig.add_subplot(gs[0, 2])
    ax4.set_title("🔍  Anomaly Detection Scores")
    cmap = plt.cm.RdYlGn_r
    scores = df["anomaly_score"].values
    ax4.scatter(minutes, scores, c=scores, cmap=cmap, s=3, alpha=0.6, vmin=0, vmax=4)
    ax4.axhline(2, color=C_ATK, lw=1.5, ls="--", label="Detection threshold")
    ax4.set_ylabel("Score (0–4 detectors)"); ax4.set_xlabel("Minute")
    ax4.legend(fontsize=8); ax4.grid(True, alpha=0.4)
    ax4.set_xticks(xticks[::3]); ax4.set_xticklabels(xlabels[::3], rotation=45)

    # ── Panel 5: Attack type distribution ────────────────────────────────
    ax5 = fig.add_subplot(gs[1, 2])
    ax5.set_title("🎯  Attack Type Distribution")
    atk_types = df[df["is_attack"]]["attack_type"].value_counts()
    if len(atk_types) > 0:
        colours = [C_ATK, C_TARGET, C_CORR, "#a78bfa"][:len(atk_types)]
        wedges, texts, autotexts = ax5.pie(
            atk_types.values, labels=atk_types.index,
            autopct="%1.0f%%", colors=colours,
            textprops={"color": C_TEXT, "fontsize": 8},
            startangle=90,
        )
        for at in autotexts: at.set_fontsize(8)
    else:
        ax5.text(0.5, 0.5, "No attacks\ninjected", ha="center", va="center",
                 color=C_DIM, transform=ax5.transAxes)
    ax5.set_facecolor(BG_CARD)

    # ── Panel 6: KPI Summary ──────────────────────────────────────────────
    ax6 = fig.add_subplot(gs[2, 2])
    ax6.axis("off")
    ax6.set_title("📈  Summary KPIs")

    kpi_lines = [
        ("Energy Saved",         f"{metrics.get('energy_saved_pct',0):.1f}%",      C_SAVE),
        ("CO₂ Avoided",          f"{metrics.get('co2_saved_kg',0):.1f} kg",         C_OPT),
        ("Cost Saved / Day",     f"{metrics.get('cost_saved_tnd_day',0):.2f} TND",  C_TARGET),
        ("Attacks Injected",     str(metrics.get("attacks_injected",0)),             C_DIM),
        ("Attacks Detected",     str(metrics.get("attacks_detected",0)),             C_ATK),
        ("Precision",            f"{metrics.get('precision',0):.1%}",               C_CORR),
        ("Recall",               f"{metrics.get('recall',0):.1%}",                  C_CORR),
        ("F1 Score",             f"{metrics.get('f1_score',0):.1%}",                C_CORR),
        ("Uptime",               f"{metrics.get('uptime_pct',100):.1f}%",           C_SAVE),
    ]
    y = 0.96
    for label, value, colour in kpi_lines:
        ax6.text(0.02, y, f"  {label}", transform=ax6.transAxes,
                 color=C_DIM, fontsize=9, va="top")
        ax6.text(0.98, y, value, transform=ax6.transAxes,
                 color=colour, fontsize=9, va="top", ha="right", fontweight="bold")
        y -= 0.10

    plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=BG_DARK)
    print(f"\n✅ Report saved to: {save_path}")
    return save_path


def print_summary(metrics: dict):
    """Print a formatted summary to the terminal."""
    print("\n" + "═" * 58)
    print("  GUARDIAN AI — SIMULATION RESULTS")
    print("═" * 58)
    print(f"  ⚡ Energy Saved          : {metrics.get('energy_saved_pct',0):>6.1f}%")
    print(f"  ⚡ Energy Saved (kWh)    : {metrics.get('energy_saved_kwh',0):>6.2f} kWh")
    print(f"  🌿 CO₂ Avoided           : {metrics.get('co2_saved_kg',0):>6.2f} kg")
    print(f"  🌿 Equivalent Trees      : {metrics.get('co2_saved_trees_equiv',0):>6.1f} trees/year")
    print(f"  💰 Cost Saved / Day      : {metrics.get('cost_saved_tnd_day',0):>6.2f} TND")
    print(f"  💰 Cost Saved / Year     : {metrics.get('cost_saved_tnd_year',0):>6.0f} TND")
    print(f"  💧 Water Saved           : {metrics.get('water_saved_m3',0):>6.2f} m³")
    print("  " + "─" * 54)
    print(f"  ⚠  Attacks Injected      : {metrics.get('attacks_injected',0):>6}")
    print(f"  🛡  Attacks Detected      : {metrics.get('attacks_detected',0):>6}")
    print(f"  🎯 Precision              : {metrics.get('precision',0):>6.1%}")
    print(f"  🎯 Recall                 : {metrics.get('recall',0):>6.1%}")
    print(f"  🎯 F1 Score               : {metrics.get('f1_score',0):>6.1%}")
    print(f"  🔒 Uptime                 : {metrics.get('uptime_pct',100):>6.1f}%")
    print("═" * 58 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Guardian AI Demo")
    parser.add_argument("--attack-prob", type=float, default=0.04,
                        help="Per-minute FDI attack probability (default: 0.04)")
    parser.add_argument("--seed",        type=int,   default=42,
                        help="Random seed (default: 42)")
    parser.add_argument("--output",      type=str,   default="guardian_ai_report.png",
                        help="Output chart filename")
    args = parser.parse_args()

    df, metrics = run_pipeline(attack_prob=args.attack_prob, seed=args.seed)
    print_summary(metrics)
    plot_results(df, metrics, save_path=args.output)


if __name__ == "__main__":
    main()
