# 🛡️ GUARDIAN AI — Pitch Deck
## Smart City Cybersecurity & Energy Optimisation · Tunisia
### AI Night Innovation Challenge 2025 · Double_A Team

---

## SLIDE 1 — TITLE

# 🛡️ GUARDIAN AI

**Smart City Security & Energy Optimisation Platform**

*Protecting Tunisia's Public Lighting & Water Infrastructure Against False Data Injection Cyber-Attacks*

> *"When the city's nervous system is under attack, Guardian AI keeps the lights on and the water flowing."*

**Double_A Team · AI Night Challenge 2025 · Tunisia**

---

## SLIDE 2 — THE PROBLEM

### Tunisian Smart Cities Are Critically Vulnerable

Tunisia's growing smart infrastructure connects thousands of IoT sensors across cities like **Tunis, Sfax, Sousse, Monastir, and Bizerte**:

- 🌆 Public street lighting networks
- 💧 Water distribution pressure & flow sensors
- ⚡ Energy grid smart meters

**The Digital Attack Surface is Enormous**

| Risk Vector | Impact |
|---|---|
| Unencrypted MQTT/HTTP sensor streams | Data interception & manipulation |
| Default firmware credentials | Remote device takeover |
| No anomaly detection at edge | Silent, long-term data poisoning |
| Centralised control without redundancy | Single point of failure = city-wide outage |

**What happens when sensors lie?**
- Triggered blackouts in residential neighbourhoods
- Masked water leaks wasting tens of thousands of m³ per day
- Energy mis-allocation causing +18% overconsumption and unnecessary CO₂

---

## SLIDE 3 — THE THREAT: FALSE DATA INJECTION (FDI)

### What is a False Data Injection Attack?

An adversary **compromises IoT sensors** and injects fabricated readings into the control system. The AI/SCADA makes decisions based on **manipulated data — not reality**.

**Example:**
```
Sensor reality: 75 kW   →   Attacker injects: 300 kW   →   System overloads the grid
```

### 4 Attack Types Guardian AI Defends Against

| Attack Type | Method | Objective | Detection Difficulty |
|---|---|---|---|
| **Spike** | Multiply reading 3–5× | Trigger grid overload | Easy |
| **Blackout Mask** | Suppress to ~0 | Hide water leaks, power theft | Medium |
| **Gradual Drift** | Slow 5–8% ramp/min | Evade threshold alarms | Hard |
| **Coordinated** | Hit lighting + water simultaneously | Simultaneous infrastructure collapse | Very Hard |

---

## SLIDE 4 — GUARDIAN AI ARCHITECTURE

### A 4-Layer Intelligent Protection System

![System Architecture](SysArch.png)

**Four layers working together:**
1. **Edge Layer** — Secure-by-design IoT sensors with hardware signing
2. **Secure Communication** — Zero-Trust, TLS 1.3, HMAC-SHA256 authentication
3. **AI Detection Engine** — Hybrid ensemble anomaly detection (4 methods)
4. **Optimisation Engine** — Adaptive energy & water management

---

## SLIDE 5 — EDGE LAYER (IoT Sensors)

### Secure-by-Design Hardware Architecture

**Components per sensor node:**
- **MCU**: ESP32-S3 or STM32WL (LoRaWAN + hardware TLS accelerator)
- **Secure Element**: ATECC608B — hardware key storage, performs HMAC signing
- **Secure Boot**: Signed firmware verified on every power-on
- **OTA Updates**: Cryptographically signed packages only

**Per-message security (every 60 seconds):**
```json
{
  "sensor_id": "LIGHT-042",
  "seq": 1847,
  "ts": 1721234567.891,
  "payload": { "kw": 73.4 },
  "hmac": "a3f9e1c2..."
}
```

- `seq` → monotonic counter (blocks replay attacks)
- `ts` → freshness timestamp (30-second sliding window)
- `hmac` → HMAC-SHA256 over the full payload (detects tampering)

---

## SLIDE 6 — SECURE COMMUNICATION LAYER

### Zero-Trust Network Architecture

**Principle:** *"Never trust, always verify"* — every message, every device, every time.

**Controls implemented:**

| Control | Technology | Purpose |
|---|---|---|
| Transport Encryption | TLS 1.3 / DTLS 1.3 | Prevent eavesdropping |
| Message Authentication | HMAC-SHA256 | Detect any tampering |
| Replay Prevention | Sequence numbers + 30s window | Block replayed packets |
| Device Identity | X.509 certificates | Only registered sensors accepted |
| Rate Limiting | Max 2 msgs/min/sensor | Prevent flooding attacks |
| Geo-fencing | GPS city bounding box | Reject out-of-area spoofed sensors |
| Sensor Trust Score | Penalty/recovery model | Auto-quarantine compromised devices |

**Trust Score System:**
- Each sensor starts at 100/100
- Each anomalous reading → −10 penalty
- Clean readings over time → gradual recovery
- Below 40 → flagged for operator review

---

## SLIDE 7 — AI DETECTION ENGINE

### Hybrid Explainable Anomaly Detection

**Why 4 detectors instead of 1?**
- Single methods have blind spots (Z-score misses gradual drift, thresholds miss coordinated attacks)
- Ensemble voting reduces false positives — critical for public infrastructure
- Every detection is **fully explainable** to engineers and auditors

**Ensemble Logic:**
```python
# Flag as attack if ≥ 2 of 4 methods agree
score = seasonal_zscore + seasonal_iqr + rate_of_change + rolling_zscore
is_attack = (score >= 2)
```

**Method Breakdown:**

| Detector | Catches | Key Insight |
|---|---|---|
| **Seasonal Z-Score** | Outliers vs hourly expected value | Uses per-hour μ/σ from 48h clean baseline |
| **Seasonal IQR Fences** | Distribution violations per hour | Hourly Q1/Q3 × 2.5 multiplier |
| **Rate-of-Change** | Sudden physical impossibilities | `\|Δx\| > μ_Δ + 5σ_Δ` |
| **Rolling Residual Z** | Gradual drift from local trend | 20-point window on de-seasonalised signal |

**Measured Performance:**

| Metric | Score |
|---|---|
| Precision | **99.6%** |
| Recall | **87.8%** |
| F1 Score | **92.9%** |
| Accuracy | **98.4%** |

**Data Correction:** Anomalies replaced by linear interpolation between last and next clean readings — transparent and auditable.

---

## SLIDE 8 — DATA FLOW

### From Sensor Reading to Safe Decision

![Data Flow](Dataflow.png)

**Pipeline (sub-second latency):**
1. Sensor publishes reading every 60 seconds
2. **HMAC verification** → reject if signature fails
3. **Replay check** → reject if sequence number already seen
4. **Rate limiter** → reject if sensor flooding
5. **FDI Detection ensemble** → flag & correct if ≥ 2 detectors agree
6. **Optimisation engine** → compute adaptive setpoints on clean data
7. **Real-time dashboard** → live updates via WebSocket

---

## SLIDE 9 — OPTIMISATION ENGINE

### Smart Energy & Water Management

**Adaptive Lighting Strategy:**

| Time Window | Power Factor | Why |
|---|---|---|
| 19:30 – 22:00 | 100% | Evening peak pedestrian traffic |
| 22:00 – 00:00 | 75% | Moderate late-night activity |
| 00:00 – 05:00 | 50% | Minimal traffic — deep night |
| 05:00 – 06:00 | 75% | Pre-dawn ramp-up |
| 06:00 – 19:30 | 10% | Daytime — safety/decorative only |

**Water Distribution:**
- Reduce pump pressure 20% during off-peak (01:00–05:00)
- Anomaly pattern detection for hidden leak identification

**Measured Results (24h simulation, per zone):**

| Metric | Value |
|---|---|
| Baseline consumption | 1,248 kWh |
| Optimised consumption | 851 kWh |
| **Energy savings** | **397 kWh (31.8%)** ✅ |
| CO₂ avoided | 236 kg/day |

---

## SLIDE 10 — CYBERSECURITY CONTROLS

### Defence-in-Depth

| Layer | Controls |
|---|---|
| **Physical** | Tamper-evident enclosures · GPS tracking |
| **Firmware** | Secure boot · Signed OTA · No default credentials |
| **Network** | TLS 1.3 · MQTT-S · Firewall rules · VPN tunnels |
| **Identity** | X.509 certificates · HMAC-SHA256 · Device allowlist |
| **Data** | End-to-end encryption · Integrity hashes |
| **AI** | Anomaly detection · Trust scoring · Auto-correction |
| **Operations** | Audit logging · Incident response · Failsafe mode |

**Compliance alignment:**
- ISO/IEC 27001 (Information Security Management)
- IEC 62443 (Industrial Automation & Control Systems Security)
- NIST Cybersecurity Framework
- Tunisian Law 2004-5 on Information Security

---

## SLIDE 11 — ECOLOGICAL IMPACT

### Guardian AI as a Climate Solution

**Scaled across Tunisian cities:**

| Metric | Per Zone / Day | 100 Zones / Year |
|---|---|---|
| Energy saved | 397 kWh | 14.5 GWh |
| CO₂ avoided | 236 kg | 8,600 tonnes |
| Water preserved | ~1,200 m³ | 43.8M m³ |
| Equivalent trees | — | 410,000 trees/yr |

**SDG Alignment:**
- 🎯 **SDG 7** — Affordable and Clean Energy
- 🎯 **SDG 11** — Sustainable Cities and Communities
- �� **SDG 13** — Climate Action
- 🎯 **SDG 6** — Clean Water and Sanitation

**Tunisia national context:**
- ANME 2030 target: 30% renewable energy share — Guardian AI directly contributes
- Supports Tunisia's NDC under the Paris Agreement
- Compatible with STEG smart grid modernisation roadmap

---

## SLIDE 12 — RESILIENCE & RECOVERY

### Staying Online During Active Attacks

**Failsafe cascade (fully automatic):**

```
Attack detected
      │
      ▼
Anomalous data → Interpolation correction   (< 1 second)
      │
      ▼
Sensor trust score penalised                (−10 points)
      │
      ▼
Trust < 40%  → Flag for operator · Last known-good value used
      │
      ▼
3+ sensors in zone  → SAFE MODE activated
                       (pre-programmed conservative setpoints,
                        zero AI dependency, city stays lit)
      │
      ▼
Alert via out-of-band channel               (independent cellular link)
```

**Recovery Time Objectives:**

| Event | Detection | Correction | Recovery |
|---|---|---|---|
| Single sensor FDI | < 2 min | Immediate (interpolation) | Automatic |
| Zone-level attack (5+ sensors) | < 5 min | Safe-mode setpoints | Operator review |
| Network partition | < 1 min | Edge cached setpoints | Auto-reconnect |

---

## SLIDE 13 — SCALABILITY FOR TUNISIA

### Built for Every Tunisian City

Guardian AI is designed from the ground up to cover Tunisia's major urban centres:

| City | Population | Smart Infrastructure Need |
|---|---|---|
| **Tunis** | 2.8M | Dense urban lighting + water grid |
| **Sfax** | 1.0M | Industrial district + port infrastructure |
| **Sousse** | 700K | Tourism zone + coastal water management |
| **Monastir** | 530K | Airport corridor + heritage lighting |
| **Bizerte** | 570K | Port + industrial IoT integration |

**Why it's realistic for Tunisia:**
- Uses off-the-shelf hardware available locally (ESP32 family)
- No proprietary cloud lock-in — runs on local servers
- Tunisian telecom infrastructure (Tunisie Telecom, Ooredoo, Orange) fully supports LoRaWAN + NB-IoT
- Aligns with Programme National Smart Cities 2022–2026
- Federated learning: city models improve together without sharing raw data

---

## SLIDE 14 — TECHNOLOGY STACK

### Built Entirely Open-Source

| Layer | Technology | Why |
|---|---|---|
| Edge MCU | ESP32-S3 / STM32WL | LoRa + TLS hardware, locally available |
| Secure Element | ATECC608B | Hardware key storage, tamper-resistant |
| Connectivity | LoRaWAN + NB-IoT | Long range, low power, SONEDE/STEG compatible |
| Message Protocol | MQTT-S (Secure) | IoT industry standard, efficient on low-bandwidth |
| Backend API | FastAPI (Python) | High-performance async, easy deployment |
| AI/ML | Custom hybrid detector (NumPy/SciPy) | No cloud ML dependency, fully explainable |
| Dashboard | Chart.js + WebSocket | Real-time browser-based, no app install needed |
| Deployment | Docker + local server | Runs on Tunisian infrastructure, no foreign cloud |

**100% open-source — zero licensing fees**

---

## SLIDE 15 — DEMO & RESULTS

### What We Built in 8 Hours

**Live system demo includes:**
- ✅ Real-time IoT sensor simulation (lighting + water, 1-min resolution)
- ✅ FDI attack injection (4 attack types, configurable probability)
- ✅ Hybrid ensemble detector running live (Precision 99.6%, F1 92.9%)
- ✅ Automatic data correction via interpolation
- ✅ Adaptive energy optimisation engine (31.8% savings)
- ✅ Real-time dashboard with WebSocket updates, attack alerts, savings counter
- ✅ Zero-Trust security layer (HMAC, replay protection, trust scoring, audit log)

**One command to run:**
```bash
python3 demo.py        # Standalone matplotlib report
uvicorn main:app       # Full FastAPI + real-time dashboard
```

> *"Guardian AI — because the city that can't trust its sensors is already under attack."*

---

*Double_A Team · AI Night Innovation Challenge 2025 · Tunisia*
*Built with: FastAPI · NumPy · SciPy · Chart.js · Open-Source only*
