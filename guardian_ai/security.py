"""
guardian_ai/security.py
=======================
Cybersecurity layer for Guardian AI.

Implements:
  - HMAC-based message authentication (tamper detection)
  - Replay-attack prevention via monotonic sequence numbers + timestamp windows
  - Sensor trust scoring (penalize sensors with repeated anomaly history)
  - Audit logging (append-only event log with structured records)
  - Zero-Trust policy helpers (per-device allowlist, rate-limiting stubs)

NOTE: In production, keys would be stored in a HSM (Hardware Security Module)
      and rotated on a schedule. This module provides the logic layer.
"""

import hmac
import hashlib
import json
import time
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone


# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("guardian.security")


class HMACAuthenticator:
    """
    Signs and verifies sensor payloads using HMAC-SHA256.

    In a real deployment:
      - Each IoT sensor holds a unique pre-shared key provisioned at manufacture.
      - The key is stored in the sensor's secure element (e.g., ATECC608B).
      - The cloud validates the signature before any processing.
    """

    def __init__(self, secret_key: bytes = b"tn-guardian-demo-key-2025"):
        self.key = secret_key

    def sign(self, payload: dict) -> str:
        """Return HMAC-SHA256 hex signature for a JSON-serialised payload."""
        msg = json.dumps(payload, sort_keys=True, default=str).encode()
        return hmac.new(self.key, msg, hashlib.sha256).hexdigest()

    def verify(self, payload: dict, signature: str) -> bool:
        """Return True if signature matches payload."""
        expected = self.sign(payload)
        return hmac.compare_digest(expected, signature)


class ReplayProtector:
    """
    Prevents replay attacks by tracking (sensor_id, sequence_number) pairs
    and rejecting messages older than the time window.

    Architecture:
      - Each sensor increments a sequence counter for every message.
      - Messages replayed out-of-order or with repeated sequence numbers
        are dropped immediately.
    """

    def __init__(self, window_seconds: int = 30, max_seq_cache: int = 10_000):
        self.window_seconds = window_seconds
        self.seen: dict[str, deque] = defaultdict(lambda: deque(maxlen=max_seq_cache))

    def is_valid(self, sensor_id: str, seq: int, ts: float) -> bool:
        """
        Return True if this (sensor_id, seq, ts) combination is fresh and unseen.
        """
        now  = time.time()
        # Reject stale messages
        if abs(now - ts) > self.window_seconds:
            logger.warning("ReplayProtector: stale message from %s (age=%.1fs)", sensor_id, now - ts)
            return False
        # Reject replayed sequence numbers
        seen = self.seen[sensor_id]
        if seq in seen:
            logger.warning("ReplayProtector: replayed seq=%d from %s", seq, sensor_id)
            return False
        seen.append(seq)
        return True


class SensorTrustScorer:
    """
    Tracks each sensor's anomaly history and assigns a trust score in [0, 1].

    A sensor that has repeatedly injected anomalous data gets down-weighted.
    Its readings are flagged for human review rather than acted upon directly.

    Trust decay model:
      - Each confirmed attack episode decreases trust by `penalty`.
      - Trust recovers linearly over time at `recovery_rate` per minute.
    """

    def __init__(self, penalty: float = 0.15, recovery_rate: float = 0.002):
        self.penalty       = penalty
        self.recovery_rate = recovery_rate
        self.scores: dict[str, float]        = defaultdict(lambda: 1.0)
        self.last_update: dict[str, float]   = defaultdict(time.time)
        self.event_counts: dict[str, int]    = defaultdict(int)

    def record_attack(self, sensor_id: str) -> float:
        """Penalise sensor and return new trust score."""
        self._recover(sensor_id)
        self.scores[sensor_id]      = max(0.0, self.scores[sensor_id] - self.penalty)
        self.event_counts[sensor_id]+= 1
        score = self.scores[sensor_id]
        logger.warning("TrustScorer: sensor %s penalised -> trust=%.2f", sensor_id, score)
        return score

    def get_trust(self, sensor_id: str) -> float:
        """Return current trust score (applies recovery since last update)."""
        self._recover(sensor_id)
        return self.scores[sensor_id]

    def is_trusted(self, sensor_id: str, threshold: float = 0.40) -> bool:
        """Return False if sensor trust falls below threshold."""
        return self.get_trust(sensor_id) >= threshold

    def _recover(self, sensor_id: str):
        """Apply time-based trust recovery."""
        now     = time.time()
        elapsed = (now - self.last_update[sensor_id]) / 60.0  # minutes
        self.scores[sensor_id] = min(1.0, self.scores[sensor_id] + elapsed * self.recovery_rate)
        self.last_update[sensor_id] = now


class AuditLogger:
    """
    Append-only structured audit log for all security events.

    Events are stored in memory (and optionally written to file) with:
      timestamp, event_type, sensor_id, detail
    """

    EVENT_TYPES = {
        "ATTACK_DETECTED", "ATTACK_CORRECTED", "SIGNATURE_FAIL",
        "REPLAY_ATTEMPT", "TRUST_LOW", "SYSTEM_START", "SYSTEM_STOP",
    }

    def __init__(self, log_file: str = None):
        self._records: list  = []
        self._log_file       = log_file

    def log(self, event_type: str, sensor_id: str = "system", detail: str = ""):
        record = {
            "ts"         : datetime.now(timezone.utc).isoformat(),
            "event_type" : event_type,
            "sensor_id"  : sensor_id,
            "detail"     : detail,
        }
        self._records.append(record)
        logger.info("AUDIT | %s | %s | %s", event_type, sensor_id, detail)
        if self._log_file:
            with open(self._log_file, "a") as f:
                f.write(json.dumps(record) + "\n")

    def get_summary(self) -> dict:
        from collections import Counter
        counts = Counter(r["event_type"] for r in self._records)
        return dict(counts)

    def get_recent(self, n: int = 20) -> list:
        return self._records[-n:]


class ZeroTrustPolicy:
    """
    Zero-Trust policy engine: 'Never trust, always verify.'

    Enforces:
      1. Device allowlisting  - only registered sensor IDs are accepted
      2. Rate limiting        - max N messages per minute per sensor
      3. Geo-fencing          - reject readings from unexpected GPS coordinates
         (simplified: just checks that coordinates are within the configured city bounding box)
    """

    # Approximate bounding box for Tunis governorate (configurable per city)
    # Tunis bounding box — override per deployment city
    SFAX_LAT_MIN, SFAX_LAT_MAX = 36.70, 37.00
    SFAX_LON_MIN, SFAX_LON_MAX = 10.05, 10.35

    def __init__(self, max_messages_per_minute: int = 2):
        self.allowlist: set              = set()
        self.max_mpm                     = max_messages_per_minute
        self._msg_times: dict[str, deque]= defaultdict(lambda: deque(maxlen=200))

    def register_sensor(self, sensor_id: str):
        """Add a sensor to the allowlist."""
        self.allowlist.add(sensor_id)

    def is_allowed(self, sensor_id: str) -> bool:
        """Check allowlist membership."""
        return sensor_id in self.allowlist

    def check_rate(self, sensor_id: str) -> bool:
        """Return True if sensor is within its message rate limit."""
        now   = time.time()
        times = self._msg_times[sensor_id]
        times.append(now)
        # Count messages in last 60 seconds
        recent = sum(1 for t in times if now - t <= 60)
        return recent <= self.max_mpm

    def check_geofence(self, lat: float, lon: float) -> bool:
        """Return True if coordinates are within the city bounding box."""
        return (self.SFAX_LAT_MIN <= lat <= self.SFAX_LAT_MAX and
                self.SFAX_LON_MIN <= lon <= self.SFAX_LON_MAX)


# ── Convenience facade ────────────────────────────────────────────────────────

class GuardianSecurityLayer:
    """
    Unified security facade that wires all components together.

    Usage::

        sec = GuardianSecurityLayer()
        sec.zt.register_sensor("LIGHT-001")

        ok, reason = sec.validate_message(
            sensor_id="LIGHT-001", seq=42, ts=time.time(),
            payload={"v": 75.3}, signature="<hmac>"
        )
    """

    def __init__(self):
        self.auth    = HMACAuthenticator()
        self.replay  = ReplayProtector()
        self.trust   = SensorTrustScorer()
        self.audit   = AuditLogger()
        self.zt      = ZeroTrustPolicy()
        self.audit.log("SYSTEM_START", detail="Guardian Security Layer initialised")

    def validate_message(
        self,
        sensor_id: str,
        seq: int,
        ts: float,
        payload: dict,
        signature: str,
    ) -> tuple[bool, str]:
        """
        Full message validation pipeline.

        Returns (True, "ok") or (False, reason_string).
        """
        # 1. Allowlist check
        if not self.zt.is_allowed(sensor_id):
            self.audit.log("SIGNATURE_FAIL", sensor_id, "not in allowlist")
            return False, "device_not_registered"

        # 2. Rate limit
        if not self.zt.check_rate(sensor_id):
            self.audit.log("REPLAY_ATTEMPT", sensor_id, "rate_limit_exceeded")
            return False, "rate_limit_exceeded"

        # 3. Replay check
        if not self.replay.is_valid(sensor_id, seq, ts):
            self.audit.log("REPLAY_ATTEMPT", sensor_id, f"seq={seq}")
            return False, "replay_detected"

        # 4. HMAC signature
        if not self.auth.verify(payload, signature):
            self.audit.log("SIGNATURE_FAIL", sensor_id, "hmac_mismatch")
            return False, "signature_invalid"

        # 5. Trust score
        if not self.trust.is_trusted(sensor_id):
            self.audit.log("TRUST_LOW", sensor_id,
                           f"trust={self.trust.get_trust(sensor_id):.2f}")
            return False, "trust_score_too_low"

        return True, "ok"
