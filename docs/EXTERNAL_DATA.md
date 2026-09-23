# AegisFlight — External (real-flight) data: research, compatibility, validation

> **Scope.** Analysis-only use of *public* data. Nothing here trains, tunes or
> re-thresholds the production IDS, and nothing touches the synthetic benchmark
> splits. Every number quoted in this area of the docs lives in a **generated**
> file under `artifacts/external/` (produced by `scripts/external_validation.py`).

## 1. Dataset research (Phase 1)

Access was checked on 2026-09-23. "Real" is only stated where the source
establishes it.

| Dataset | Source | Real / synthetic | Platform · FC | Protocol / format | Attacks | Benign | Licence / access | Size | Programmatic? | AegisFlight use |
|---|---|---|---|---|---|---|---|---|---|---|
| **PX4 Flight Review public logs** | [review.px4.io](https://review.px4.io/) (`/dbinfo` metadata API) · [PX4 log docs](https://docs.px4.io/main/en/log/flight_log_analysis) | Uploaded logs: **mix of real, SITL and HITL** (must be filtered — see §4) | many multirotors / FW / VTOL · PX4 | ULog (on-board log, *not* the MAVLink link) | none | presumed (no ground truth) | public uploads; no dataset licence stated → analysed locally, not redistributed | 468,513 public logs listed | **yes** | **Imported** → external benign validation of navigation features (E1) |
| **ALFA** (Keipour, Mousaei, Scherer, IJRR 2021) | [doi:10.1184/R1/12707963.v1](https://doi.org/10.1184/R1/12707963.v1) · [paper](https://arxiv.org/abs/1907.06268) · [tools](https://github.com/castacks/alfa-dataset-tools) | **Real** autonomous flights (paper) | Carbon Z T-28 fixed-wing · Pixhawk, modified ArduPilot 3.9 | **MAVLink `.tlog` recorded at the GCS**; ROS/mavros CSV/bag/mat | none (engine / elevator / aileron / rudder **faults**) | 10 no-failure sequences + pre-fault segments | CC BY 4.0 on figshare (bundled README says CC0) | telemetry 211 MB, processed 272 MB | **yes** | **Imported** → full-pipeline replay on a real link (E2); fault-response comparison |
| **UAV Attack Dataset** (Whelan et al. 2020) | [IEEE DataPort, doi:10.21227/00dg-0d12](https://ieee-dataport.org/open-access/uav-attack-dataset) · paper: *Novelty-based Intrusion Detection of Sensor Attacks on UAVs* (ACM Q2SWinet 2020) | SITL/HITL **and live** (Holybro S500, Pixhawk 4) | multirotor · PX4 | ULog + CSV | **GPS spoofing (live, HackRF), GPS jamming, ping DoS (sim)** | yes | open access but **requires an IEEE account login** | 684 MB | no (login) | **Best candidate for real *attack* validation** — not imported; our ULog adapter is format-compatible |
| HITL UAV DoS & GPS-spoofing (Park, Park, Kim 2020) | [arXiv:2011.00540](https://arxiv.org/pdf/2011.00540) | **Synthetic (HITL, jMAVSim)** | PX4 | ULog-derived features | DoS, GPS spoofing | 1 benign log | uses the DataPort data above | 3 logs | via DataPort | comparison only |
| MAVLink Message ID Sequence | [IEEE DataPort, doi:10.21227/mhpm-g592](https://ieee-dataport.org/documents/mavlink-message-id-sequence-dataset) · GUIDE, *Computers & Security* 2024 | **Synthetic (HITL)** | PX4 HITL | MAVLink message-ID sequences (.npy) + pcap | active network attacks (per paper) | yes | **subscription** | ~57 MB pcap | no | comparison only (message-mix features) |
| UAV-SEAD (Kabaoglu & Sariel 2026) | [Hugging Face](https://huggingface.co/datasets/aykutkabaoglu/uav-flight-anomaly-dataset) | **Real** PX4 fleet flights (dataset card) | multirotors · PX4 | ULog (+ label mapping) | none (state-estimation *anomalies*) | yes | CC BY 4.0 | ~30 GB, 1,396 labelled logs | yes | strong next step for labelled real benign/anomaly validation of navigation features (not imported: size/time) |
| RflyMAD (Le et al., IJRR 2025) | [arXiv:2311.11340](https://arxiv.org/abs/2311.11340) · [download page](https://rfly-openha.github.io/documents/4_resources/dataset.html) | 497 **real** + 5,132 SIL/HIL cases | multicopter · PX4 | ULog + telemetry logs | none (11 fault types incl. sensor faults) | yes | per site | 114 GB | via site | future: sensor-inconsistency vs attack discrimination |
| Cyber-Physical UAV dataset (Hassler, Mughal, Ismail, IEEE T-ITS 2023) | [GitHub](https://github.com/uamughal/UAVs-Dataset-Under-Normal-and-Cyberattacks) | **Real** testbed | consumer UAV over **Wi-Fi** | CSV (37 cyber = Wi-Fi/IP frame fields, 16 physical) | de-auth DoS, replay, FDI, evil twin | yes | MIT | 54,784 rows | yes (git) | comparison only — not MAVLink, feature schema incompatible |
| ECU-IoFT (Applied Sciences 2022) | [GitHub](https://github.com/CSCRC-SCREED/ECU-IoFT) | **Real** | low-end educational drone, **Wi-Fi** | CSV of network traffic | 3 Wi-Fi attacks | yes | per repo | 8.7 MB | yes (git) | comparison only — not MAVLink |
| TEXBAT (UT Austin Radionavigation Lab) | [radionavlab.ae.utexas.edu/texbat](https://radionavlab.ae.utexas.edu/texbat/) | **Real RF** recordings | GNSS receiver (static/dynamic) | raw IQ | GPS spoofing scenarios | clean scenarios | per site | very large | via site | comparison only — signal level, below our telemetry abstraction |
| GPS spoofing on UAS (Aissou, Mendeley Data) | [data.mendeley.com/datasets/z7dj3yyzt8/3](https://data.mendeley.com/datasets/z7dj3yyzt8/3) | authentic signals + **simulated** attacks | 8-channel GPS receiver | receiver-channel features | simplistic / intermediate / sophisticated spoofing | yes | per site | — | via site | comparison only — receiver level |
| DJI flight plans under attack (Watkins, NDSS-DISS 2020) | [Zenodo 3634048](https://zenodo.org/records/3634048) | **Real** | DJI Phantom 4 / Spark | CSV | GPS spoofing, IR / white light, Wi-Fi de-auth | yes | CC BY 4.0 | 5.9 MB | yes | comparison only — DJI, not MAVLink |

Excluded GitHub test fixtures: `UAVLogViewer/src/assets/vtol.tlog` (ArduPilot
**SITL**: `SIM_*` parameters, SITL home location); `dronekit-la/test/logs/flight.tlog`
(looks like real ArduCopter hardware but provenance is undocumented); `pyulog/test/*.ulg`
(mixed SITL/hardware snippets, most without GNSS).

## 2. Feature compatibility audit (Phase 2)

**A** raw field directly available · **B** derivable from raw data · **C** unavailable ·
**D** computable but must **not** be compared with the simulator (different meaning).

| ML feature | PX4 ULog (Flight Review, UAV-SEAD, Whelan) | ALFA `.tlog` (real MAVLink link) | Wi-Fi datasets (Hassler, ECU-IoFT) | GNSS RF / receiver (TEXBAT, Aissou) |
|---|---|---|---|---|
| `msg_rate_hz` | C (on-board log, no link) | B — but benign level is **vehicle-specific** (stream-rate config) → sim threshold not transferable (D for thresholds) | C (Wi-Fi frames ≠ MAVLink) | C |
| `interarrival_jitter_ms` | C | B | C | C |
| `max_seq_gap` | C | B (per-source MAVLink `seq`) | C | C |
| `loss_ratio` | C | B | C | C |
| `cmd_rate_hz` | C | A/B (`COMMAND_LONG`/`SET_MODE` present) — real **legitimate** commands exist; the simulator never sends any | C | C |
| `pos_residual_m` | B — M1 (EKF pos vs EKF vel): **D**, both from one estimator; M2 (raw GNSS pos vs GNSS vel): B | B, but GLOBAL_POSITION_INT pos & vel are both EKF outputs → **D** | C | C |
| `gps_vfr_speed_diff_ms` | M1: **D** (PX4 `VFR_HUD.groundspeed` = ‖EKF v‖ = GLOBAL_POSITION_INT v — degenerate); M2: B | **D** (ArduPilot VFR_HUD and GLOBAL_POSITION_INT both from AHRS) | C | C |
| `gps_baro_alt_diff_m` | M1: **D** (PX4 `VFR_HUD.alt` = EKF altitude); M2 raw: **D** (pressure-altitude offset of tens of m); M2b (causal offset removal): B | **D** (both AHRS) | C | C |
| `alt_rate_ms` | B | B | C | C |
| `accel_ms2` | B | B (fixed-wing dynamics) | C | C |
| `yaw_course_diff_deg` | B, but multirotors may yaw independently of course → partly D | B (fixed-wing crab angle — closest to the sim's assumption) | C | C |

PX4 mappings are defined in `src/aegisflight/external/ulog_adapter.py` from PX4
source (`GLOBAL_POSITION_INT.hpp`, `VFR_HUD.hpp` in `src/modules/mavlink/streams/`).

**Key finding already visible from the audit:** the simulator treats the GLOBAL_POSITION_INT
and VFR_HUD channels as *independent* sensors. On real PX4 and ArduPilot telemetry both are
outputs of the same estimator, so three of the six navigation cross-checks
(`pos_residual_m`, `gps_vfr_speed_diff_ms`, `gps_baro_alt_diff_m`) lose their independence on
a real link. A real deployment would have to cross-check GPS_RAW_INT (raw receiver) and
SCALED_PRESSURE (raw baro) against the EKF instead. See §5.

## 3. Experiment design (Phase 3)

Following the requested hierarchy: validation and distribution comparison first; **no
retraining** (the feature schema is only partially available, and the ML model's 5 network
features cannot be reconstructed from ULogs — imputing them would be fabrication).

| Id | Data | Question | Pipeline | Ground truth | Output |
|---|---|---|---|---|---|
| E1 | PX4 Flight Review ULogs (protocol v2 sample) | Do the simulator's benign navigation-feature distributions and the production physics thresholds hold on real multirotor flights? | ULog → synthesized navigation `MessageEnvelope`s (3 mappings) → **production** `FeatureExtractor` + `PhysicsDetector`; ML only as an explicitly labelled *navigation probe* (network features held at training mean) | presumed benign (public uploads; no attack labels) — so every alarm is counted as a *false-alarm candidate* | `artifacts/external/px4_review_v2/` |
| E2 | ALFA `.tlog` (41 files) | What does the **unchanged full IDS** do on a real MAVLink link? How does it react to real *physical faults*? | `.tlog` → `MessageEnvelope` (real timing, seq, source ids) → **unchanged `IDSPipeline`** | authors' labels: no-failure sequences + pre-fault segments = benign; post-onset = fault; rest unlabelled | `artifacts/external/alfa/` |
| E2b | ALFA `.tlog`, **held-out dates** | After the minimum per-vehicle calibration any deployment needs (one transport parameter), what is the real-link false-alarm rate? | as E2, but `protocol.nominal_msg_rate_hz` := median benign airborne rate measured on the *calibration dates only* (2018-07-18/30), `max_msg_rate_hz` scaled by the same ratio; **ML off** (its network features are simulator-specific; retraining not done) | as E2 | `artifacts/external/alfa_calibrated/` |

Sim reference for E1: 12 benign simulated flights generated exactly like the training data
but with fresh seeds (9001–9012).

## 4. What was imported (Phase 4) and provenance

Raw files: `data/external/raw/` (gitignored). Manifests with URL, bytes, SHA-256 and
retrieval time: `data/external/manifests/{alfa,px4_review_v1,px4_review_v2}.json` (committed).

**PX4 selection protocols (pre-registered in code, `external/px4_review.py`):**
* **v1** (uploader-rated "good/great" logs only) was run first. Its generated result
  (`artifacts/external/px4_review_v1/summary.md`) shows why it failed: the rated pool was tiny
  and dominated by one HITL uploader — the loader's `SYS_HITL` check rejected 38/40 logs and the
  remaining 2 had no GNSS topics → **0 usable real flights**. Kept for transparency.
* **v2** drops the rating requirement, rejects HITL/SIH airframes at selection, requires zero
  logged errors, and keeps **one log per vehicle UUID** so a single fleet cannot dominate;
  deterministic `random.Random(2026).sample` of 40.

## 5. Results

Generated summaries (the only source of numbers):

* E1 — [`artifacts/external/px4_review_v2/summary.md`](../artifacts/external/px4_review_v2/summary.md)
* E1 (failed protocol v1) — [`artifacts/external/px4_review_v1/summary.md`](../artifacts/external/px4_review_v1/summary.md)
* E2 — [`artifacts/external/alfa/summary.md`](../artifacts/external/alfa/summary.md)

* E2b (held-out dates, calibrated link, ML off) — [`artifacts/external/alfa_calibrated/summary.md`](../artifacts/external/alfa_calibrated/summary.md)

### What the real data says (read the numbers in the files above)

1. **Production thresholds do not transfer to a real link (E2).** On author-labelled benign
   ALFA periods the unchanged IDS alarms on essentially every decision. The evidence column
   shows why: the *message-rate spike* rule and the ML score. The real ArduPilot link carries
   several times the simulator's nominal message rate (`real_link_stats_airborne` vs
   `protocol.nominal_msg_rate_hz`), which also puts the ML's rate/jitter features far outside
   their simulated training range.
2. **With one documented calibration parameter and ML off (E2b), the real-link false-alarm
   rate on held-out dates drops to the sub-percent level**; the residual alarms on benign
   periods come from the physics layer (implausible acceleration / heading-course on a
   fixed-wing). On the ground (unlabelled) the protocol layer still fires — e.g. GCS
   parameter downloads look like a message flood.
3. **Physical faults are mostly *not* flagged (E2b)** — few of the fault events trigger any
   alarm. That is consistent with an IDS built for cyber signatures, but it also means the
   physics checks are not a fault detector, and faults vs attacks remain undistinguished.
4. **Real multirotors (E1)**: under PX4's real telemetry semantics (`px4_telemetry`) the
   GPS/VFR speed and GPS/baro altitude features collapse to ~0 (same estimator) and the
   position residual is small — the three cross-checks cannot fire, i.e. they would also
   miss a spoof that the EKF absorbs. The physics alarms that *do* occur are dominated by
   the heading-vs-course rule (multirotors yaw independently of their track). With raw
   GNSS/baro channels (`independent_sensors`) the uncorrected barometer offset trips the
   GPS/baro check on almost every flight; removing the offset causally
   (`independent_sensors_biascorr`) reduces but does not remove it.
5. **Sample quality matters:** many public logs have no GNSS topic (indoor / no-GPS flights)
   or long estimator-invalid periods; these are excluded and listed per mapping. Protocol v1
   produced zero real flights.

Evidence levels and report wording: `docs/VALIDATION_EVIDENCE.md`.

## 6. Reproduce

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e ".[external]"                             # adds pyulog
python scripts\fetch_external_data.py --alfa --px4 40 --px4-protocol v2
python scripts\external_validation.py --px4 --px4-protocol v2 --alfa --workers 8   # E1 + E2 + E2b
python scripts\external_validation.py --px4 --px4-protocol v1 --workers 8          # failed protocol, for transparency
```

## 7. Limitations

* **No real attack data was imported.** The only public dataset with *live* UAV attacks on a
  MAVLink/PX4 stack found (UAV Attack Dataset) requires an IEEE account; it is the top
  follow-up. Real-data results therefore measure **false alarms and fault reactions**, not
  attack detection.
* PX4 Flight Review uploads are *presumed* benign; they carry no ground truth.
* ULogs contain no link, so E1 cannot say anything about the protocol detector or the 5
  network ML features. E2 (ALFA) covers the link but is a fixed-wing ArduPlane from 2018.
* ALFA faults are physical, not cyber. Flagging them is expected behaviour for an
  anomaly-based IDS, but the IDS has no "fault" class, so it attributes them to an attack class.
