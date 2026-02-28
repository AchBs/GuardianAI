"""
guardian_ai/simulator.py
========================
IoT Sensor Data Simulator for Tunisian Smart City Infrastructure.

Generates realistic 24-hour sensor readings for:
  - Public lighting (kW consumption per street zone)
  - Water distribution (L/min flow per district)

Simulates False Data Injection (FDI) attacks:
  - spike         : sudden multiplier surge -> triggers fake demand
  - blackout_mask : suppresses readings    -> hides leaks/outages
  - gradual_drift : slow ramp              -> evades threshold detection
  - coordinated   : simultaneous attack on lighting AND water
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random


class TunisianCitySimulator:
    """
    Simulates IoT sensor streams from a Tunisian smart city network.

    Parameters
    ----------
    seed         : int  - reproducibility seed
    freq_minutes : int  - sampling frequency in minutes (default 1 = 1440 pts/day)
    """

    def __init__(self, seed: int = 42, freq_minutes: int = 1):
        np.random.seed(seed)
        random.seed(seed)
        self.freq_minutes = freq_minutes

    # ------------------------------------------------------------------
    # Private: realistic consumption patterns (Tunisia)
    # ------------------------------------------------------------------

    def _lighting_kw(self, hour: float) -> float:
        """
        Public-lighting demand curve (kW per zone).
        Active from sunset (~19:30) to sunrise (~05:30).
        Peak at ~21:00 when foot traffic is highest.
        """
        # Night period: high load with sinusoidal peak around 21h
        if hour >= 19.5 or hour <= 5.5:
            # Map hour to [0, pi] over the night window (19.5 -> 05.5 = 10h)
            if hour >= 19.5:
                t = hour - 19.5
            else:
                t = hour + 4.5   # after midnight
            base = 70.0 + 18.0 * np.sin(np.pi * t / 10.0)
            return max(5.0, base + np.random.normal(0, 2.5))
        # Day period: minimal decorative/maintenance load
        else:
            return max(0.0, 12.0 + 3.0 * np.random.normal(0, 1))

    def _water_lpm(self, hour: float) -> float:
        """
        Water flow rate (L/min) per distribution zone.
        Morning peak  06:00-09:00 (domestic + commercial opening).
        Evening peak  18:00-21:00 (domestic, irrigation).
        Overnight low 00:00-05:00.
        """
        morning = 65.0 * np.exp(-0.5 * ((hour - 7.5) / 1.4) ** 2)
        evening = 55.0 * np.exp(-0.5 * ((hour - 19.5) / 1.6) ** 2)
        midday  = 20.0 * np.exp(-0.5 * ((hour - 12.5) / 1.2) ** 2)
        base    = 18.0
        noise   = np.random.normal(0, 3.0)
        return max(0.0, base + morning + evening + midday + noise)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_normal_data(self, hours: int = 24) -> pd.DataFrame:
        """
        Generate a clean (attack-free) 24-hour sensor dataset.

        Returns
        -------
        pd.DataFrame with columns:
            timestamp, lighting_kw, water_lpm, is_attack, attack_type
        """
        n_points = hours * 60 // self.freq_minutes
        start    = datetime(2025, 7, 15, 0, 0, 0)   # Summer day, Tunisia

        timestamps, lighting, water = [], [], []

        for i in range(n_points):
            ts   = start + timedelta(minutes=i * self.freq_minutes)
            hour = ts.hour + ts.minute / 60.0
            timestamps.append(ts)
            lighting.append(self._lighting_kw(hour))
            water.append(self._water_lpm(hour))

        return pd.DataFrame({
            "timestamp"  : timestamps,
            "lighting_kw": lighting,
            "water_lpm"  : water,
            "is_attack"  : False,
            "attack_type": "none",
        })

    def inject_fdi_attacks(
        self,
        df: pd.DataFrame,
        attack_probability: float = 0.04,
        attack_types: list = None,
    ) -> pd.DataFrame:
        """
        Inject False Data Injection (FDI) attacks into sensor readings.

        Parameters
        ----------
        attack_probability : float
            Per-minute probability that a new attack episode begins.
        attack_types : list
            Subset of ['spike','blackout_mask','gradual_drift','coordinated'].

        Returns
        -------
        Modified DataFrame with added columns:
            original_lighting, original_water  (ground-truth values)
        """
        if attack_types is None:
            attack_types = ["spike", "blackout_mask", "gradual_drift", "coordinated"]

        df = df.copy()
        df["attack_type"]      = "none"
        df["is_attack"]        = False
        df["original_lighting"]= df["lighting_kw"].copy()
        df["original_water"]   = df["water_lpm"].copy()

        i = 0
        while i < len(df):
            if random.random() < attack_probability:
                atype    = random.choice(attack_types)
                duration = random.randint(4, 18)   # 4-18 minute episodes
                end      = min(i + duration, len(df))

                indices = list(range(i, end))

                if atype == "spike":
                    # Adversary injects inflated readings -> wasteful allocation
                    mult = random.uniform(2.8, 4.5)
                    df.loc[indices, "lighting_kw"] = (
                        df.loc[indices, "lighting_kw"] * mult
                    )
                    df.loc[indices, "water_lpm"] = (
                        df.loc[indices, "water_lpm"] * random.uniform(1.5, 2.5)
                    )

                elif atype == "blackout_mask":
                    # Adversary suppresses readings -> hides leaks / power theft
                    df.loc[indices, "lighting_kw"] = (
                        df.loc[indices, "lighting_kw"] * random.uniform(0.0, 0.15)
                    )
                    df.loc[indices, "water_lpm"] = (
                        df.loc[indices, "water_lpm"] * random.uniform(0.0, 0.12)
                    )

                elif atype == "gradual_drift":
                    # Slow ramp -> evades static thresholds
                    for j, idx in enumerate(indices):
                        factor = 1.0 + j * random.uniform(0.04, 0.08)
                        df.at[idx, "lighting_kw"] *= factor
                        df.at[idx, "water_lpm"]   *= factor

                elif atype == "coordinated":
                    # Simultaneous attack: blackout lighting + flood water signal
                    df.loc[indices, "lighting_kw"] = (
                        df.loc[indices, "lighting_kw"] * random.uniform(0.0, 0.2)
                    )
                    df.loc[indices, "water_lpm"] = (
                        df.loc[indices, "water_lpm"] * random.uniform(4.0, 6.0)
                    )

                df.loc[indices, "is_attack"]   = True
                df.loc[indices, "attack_type"] = atype

                i = end   # skip past attack window
            else:
                i += 1

        return df
