"""
guardian_ai/detector.py
=======================
Hybrid FDI Anomaly Detection Engine (no sklearn required).

Core innovation: SEASONAL-AWARE detection.
  - Fits a 24-hour periodic profile from clean training data
  - Detects anomalies as deviations from EXPECTED value at that hour
  - Eliminates false positives caused by normal day/night transitions

Detection pipeline:
  1. Seasonal Z-Score    - deviation from hourly expected value (primary)
  2. IQR Seasonal        - hourly IQR fences (secondary)
  3. Rate-of-Change      - flags sudden unphysical jumps (tertiary)
  4. Rolling Residual Z  - sliding window on de-seasonalised residuals (tertiary)

Ensemble rule: flag a point as anomalous if >= 2 of 4 detectors agree.
"""

import numpy as np
import pandas as pd


class FDIDetector:
    """
    Explainable hybrid seasonal anomaly detector for FDI attack identification.

    All methods are transparent and explainable:
      - Every flag has a named reason (L:seasonal-z, W:IQR, etc.)
      - Seasonal awareness eliminates most false positives from natural cycles
      - Trained on clean reference data for maximum sensitivity
    """

    def __init__(
        self,
        seasonal_z_threshold:  float = 4.0,   # σ from hourly mean -> flag
        iqr_multiplier:        float = 2.5,   # IQR fence multiplier
        roc_sigma:             float = 5.0,   # RoC: σ from mean diff -> flag
        rolling_window:        int   = 20,    # rolling residual window
        rolling_threshold:     float = 4.0,   # rolling residual z threshold
        min_detectors:         int   = 2,     # ensemble min votes
    ):
        self.seasonal_z_threshold = seasonal_z_threshold
        self.iqr_multiplier       = iqr_multiplier
        self.roc_sigma            = roc_sigma
        self.rolling_window       = rolling_window
        self.rolling_threshold    = rolling_threshold
        self.min_detectors        = min_detectors

        self._baseline: dict = {}
        self._fitted         = False

    # ------------------------------------------------------------------
    # Training on clean reference data
    # ------------------------------------------------------------------

    def fit(self, clean_df: pd.DataFrame) -> "FDIDetector":
        """
        Compute seasonal baselines from a CLEAN (attack-free) reference dataset.

        Stores:
          - Per-hour mean, std, Q1, Q3 (for seasonal-aware detection)
          - Global MAD and diff statistics (for RoC detection)
        """
        for col in ("lighting_kw", "water_lpm"):
            vals  = clean_df[col].values.astype(float)
            hours = clean_df["timestamp"].dt.hour.values

            # Per-hour statistics (seasonal profile)
            hourly = {}
            for h in range(24):
                mask = hours == h
                hv   = vals[mask]
                if len(hv) < 3:
                    hv = vals   # fallback: use global
                q1, q3 = np.percentile(hv, 25), np.percentile(hv, 75)
                hourly[h] = {
                    "mean" : float(np.mean(hv)),
                    "std"  : float(np.std(hv) + 1e-9),
                    "q1"   : float(q1),
                    "q3"   : float(q3),
                    "iqr"  : float(q3 - q1 + 1e-9),
                }

            # Global RoC statistics (diff-based, not seasonal)
            diffs = np.abs(np.diff(vals, prepend=vals[0]))
            self._baseline[col] = {
                "hourly"   : hourly,
                "roc_mean" : float(np.mean(diffs)),
                "roc_std"  : float(np.std(diffs) + 1e-9),
            }

        self._fitted = True
        return self

    # ------------------------------------------------------------------
    # Individual detectors
    # ------------------------------------------------------------------

    def _seasonal_zscore(
        self, values: np.ndarray, hours: np.ndarray, col: str
    ) -> np.ndarray:
        """
        Compare each reading to the EXPECTED VALUE for that hour.
        False-positive proof against day/night transitions.
        """
        flags = np.zeros(len(values), dtype=bool)
        if not (self._fitted and col in self._baseline):
            # Fallback: global modified z-score
            med = np.median(values)
            mad = np.median(np.abs(values - med)) + 1e-9
            flags = np.abs(values - med) / (1.4826 * mad) > self.seasonal_z_threshold
            return flags

        hourly = self._baseline[col]["hourly"]
        for i, (val, h) in enumerate(zip(values, hours)):
            hstat = hourly[h]
            z     = abs(val - hstat["mean"]) / hstat["std"]
            flags[i] = z > self.seasonal_z_threshold
        return flags

    def _seasonal_iqr(
        self, values: np.ndarray, hours: np.ndarray, col: str
    ) -> np.ndarray:
        """Hourly IQR fences."""
        flags = np.zeros(len(values), dtype=bool)
        if not (self._fitted and col in self._baseline):
            q1, q3 = np.percentile(values, 25), np.percentile(values, 75)
            iqr    = q3 - q1 + 1e-9
            flags  = (values < q1 - self.iqr_multiplier * iqr) | \
                     (values > q3 + self.iqr_multiplier * iqr)
            return flags

        hourly = self._baseline[col]["hourly"]
        for i, (val, h) in enumerate(zip(values, hours)):
            hstat  = hourly[h]
            lower  = hstat["q1"] - self.iqr_multiplier * hstat["iqr"]
            upper  = hstat["q3"] + self.iqr_multiplier * hstat["iqr"]
            flags[i] = (val < lower) or (val > upper)
        return flags

    def _rate_of_change(self, values: np.ndarray, col: str) -> np.ndarray:
        """
        Rate-of-change using globally fitted diff statistics.
        Catches sudden spikes and coordinated attacks.
        """
        diffs = np.abs(np.diff(values, prepend=values[0]))
        if self._fitted and col in self._baseline:
            mu_d  = self._baseline[col]["roc_mean"]
            sig_d = self._baseline[col]["roc_std"]
        else:
            mu_d  = np.mean(diffs)
            sig_d = np.std(diffs) + 1e-9
        return diffs > (mu_d + self.roc_sigma * sig_d)

    def _rolling_residual_z(
        self, values: np.ndarray, hours: np.ndarray, col: str
    ) -> np.ndarray:
        """
        Rolling z-score on de-seasonalised RESIDUALS.
        Catches gradual drift that shifts the series above the expected pattern.

        Residual = actual - expected_hourly_mean
        Rolling z = |residual - rolling_mean_residual| / rolling_std_residual
        """
        # Compute residuals (deviation from expected hourly mean)
        residuals = np.zeros(len(values))
        if self._fitted and col in self._baseline:
            hourly = self._baseline[col]["hourly"]
            for i, (val, h) in enumerate(zip(values, hours)):
                residuals[i] = val - hourly[h]["mean"]
        else:
            residuals = values - np.mean(values)

        s     = pd.Series(residuals)
        rmean = s.rolling(self.rolling_window, min_periods=5).mean().bfill().values
        rstd  = s.rolling(self.rolling_window, min_periods=5).std().bfill().values + 1e-9
        return np.abs(residuals - rmean) / rstd > self.rolling_threshold

    # ------------------------------------------------------------------
    # Ensemble
    # ------------------------------------------------------------------

    def _detect_column(
        self, values: np.ndarray, hours: np.ndarray, col: str
    ) -> tuple:
        d1 = self._seasonal_zscore(values, hours, col)
        d2 = self._seasonal_iqr(values, hours, col)
        d3 = self._rate_of_change(values, col)
        d4 = self._rolling_residual_z(values, hours, col)

        scores  = d1.astype(int) + d2.astype(int) + d3.astype(int) + d4.astype(int)
        flagged = scores >= self.min_detectors

        detail = {
            "seasonal_z": d1,
            "iqr"        : d2,
            "roc"        : d3,
            "rolling_z"  : d4,
        }
        return flagged, scores, detail

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Run FDI detection.

        Requires: lighting_kw, water_lpm, timestamp columns.
        """
        df    = df.copy()
        hours = df["timestamp"].dt.hour.values

        l_vals = df["lighting_kw"].values.astype(float)
        w_vals = df["water_lpm"].values.astype(float)

        l_flag, l_score, l_det = self._detect_column(l_vals, hours, "lighting_kw")
        w_flag, w_score, w_det = self._detect_column(w_vals, hours, "water_lpm")

        df["lighting_anomaly"] = l_flag
        df["water_anomaly"]    = w_flag
        df["anomaly_score"]    = (l_score + w_score) / 2.0
        df["detected_attack"]  = l_flag | w_flag

        # Explainability labels
        reasons = []
        for i in range(len(df)):
            r = []
            if l_det["seasonal_z"][i]: r.append("L:seas-z")
            if l_det["iqr"][i]:        r.append("L:IQR")
            if l_det["roc"][i]:        r.append("L:RoC")
            if l_det["rolling_z"][i]:  r.append("L:roll-z")
            if w_det["seasonal_z"][i]: r.append("W:seas-z")
            if w_det["iqr"][i]:        r.append("W:IQR")
            if w_det["roc"][i]:        r.append("W:RoC")
            if w_det["rolling_z"][i]:  r.append("W:roll-z")
            reasons.append("|".join(r) if r else "clean")
        df["detection_reason"] = reasons
        return df

    def correct_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Replace detected anomalies with linear interpolation."""
        df   = df.copy()
        mask = df["detected_attack"]

        df["lighting_corrected"] = df["lighting_kw"].copy().astype(float)
        df["water_corrected"]    = df["water_lpm"].copy().astype(float)

        df.loc[mask, "lighting_corrected"] = np.nan
        df.loc[mask, "water_corrected"]    = np.nan

        df["lighting_corrected"] = (
            df["lighting_corrected"].interpolate("linear").bfill().ffill().clip(0, 200)
        )
        df["water_corrected"] = (
            df["water_corrected"].interpolate("linear").bfill().ffill().clip(0, 300)
        )
        return df

    def compute_detection_metrics(self, df: pd.DataFrame) -> dict:
        """Precision / Recall / F1 (requires is_attack ground-truth column)."""
        if "is_attack" not in df.columns:
            return {}

        tp = int(( df["is_attack"] &  df["detected_attack"]).sum())
        fp = int((~df["is_attack"] &  df["detected_attack"]).sum())
        fn = int(( df["is_attack"] & ~df["detected_attack"]).sum())
        tn = int((~df["is_attack"] & ~df["detected_attack"]).sum())

        precision = tp / (tp + fp + 1e-9)
        recall    = tp / (tp + fn + 1e-9)
        f1        = 2 * precision * recall / (precision + recall + 1e-9)
        accuracy  = (tp + tn) / len(df)

        return {
            "true_positives" : tp,
            "false_positives": fp,
            "false_negatives": fn,
            "true_negatives" : tn,
            "precision"      : round(precision, 3),
            "recall"         : round(recall,    3),
            "f1_score"       : round(f1,         3),
            "accuracy"       : round(accuracy,   3),
        }
