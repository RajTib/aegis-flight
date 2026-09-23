# E1 — PX4 Flight Review real flights: navigation replay (generated)

_Source manifest: `data/external/manifests/px4_review_v1.json` · public logs listed: 468513 · eligible under the selection protocol: 77 · downloaded: 40 (seed 2026, protocol `v1`)._

Network features (msg rate, jitter, sequence gaps, loss, command rate) are **not available** from an on-board ULog and are excluded. The ML column is a *navigation probe*: network features held at their benign training mean (z = 0) — it is **not** an ML validation.

## Exclusions (whole log)

- `370f31f0-0a27-4802-8446-82b2cd086541.ulg`: simulation build (SITL/HITL)
- `6d30dfd4-a1e1-41c8-8859-438f8cae0498.ulg`: simulation build (SITL/HITL)
- `d4e35711-1610-41c7-afe9-294f48c8b11c.ulg`: simulation build (SITL/HITL)
- `32d12bcd-d7c0-4f32-a52f-adac614f83df.ulg`: simulation build (SITL/HITL)
- `5163133a-95a9-402c-9363-4c7170a43213.ulg`: simulation build (SITL/HITL)
- `ae49f040-d4fc-444f-b87f-80ec979404ab.ulg`: simulation build (SITL/HITL)
- `c0a489d0-378e-4103-a532-59b2a8964629.ulg`: simulation build (SITL/HITL)
- `b5706710-4eef-495a-9cb6-2146c128418a.ulg`: simulation build (SITL/HITL)
- `530e12d6-7349-44c5-89aa-38125e06332c.ulg`: simulation build (SITL/HITL)
- `0004dbb9-c57b-442c-be97-3d24d722d5fa.ulg`: simulation build (SITL/HITL)
- `2824f811-342c-4b81-82f6-d421a82341a3.ulg`: simulation build (SITL/HITL)
- `3316607c-c57a-47c0-8b9a-feff89368b7d.ulg`: simulation build (SITL/HITL)
- `67cd4cf3-64b0-4719-8183-dfd83edbaeac.ulg`: simulation build (SITL/HITL)
- `ada72fd8-352b-4fa8-bb38-c0029b182c83.ulg`: simulation build (SITL/HITL)
- `19960f9c-0917-4512-ac89-4c03f7f2fc47.ulg`: simulation build (SITL/HITL)
- `ef9e101a-f8bf-407a-8278-c6db4659c96b.ulg`: simulation build (SITL/HITL)
- `dbbf3d5c-fd38-40ff-b588-df3c18157cf9.ulg`: simulation build (SITL/HITL)
- `e1009c3f-e4be-4f3f-bd68-7c8e07a0da47.ulg`: simulation build (SITL/HITL)
- `b586564f-8fe1-462e-b4e0-480775aa049b.ulg`: simulation build (SITL/HITL)
- `78d7daaa-962b-4947-9027-f30324aa02c7.ulg`: simulation build (SITL/HITL)
- `5569e544-579f-4c57-a411-198882060869.ulg`: simulation build (SITL/HITL)
- `e070ddb8-cc7a-40bd-9e33-f5ea66ae5afe.ulg`: simulation build (SITL/HITL)
- `3e4b3d06-0ea0-4607-8e04-22b5b079dd78.ulg`: simulation build (SITL/HITL)
- `f2a396e0-17bb-44a9-aa2e-745b22e2f827.ulg`: simulation build (SITL/HITL)
- `4be3c3fc-26a9-4274-86cd-d7a1683831a7.ulg`: simulation build (SITL/HITL)
- `39c74546-1959-422e-ba0e-e2db26ab9328.ulg`: simulation build (SITL/HITL)
- `42d95143-096d-4069-8e1c-63040c386537.ulg`: simulation build (SITL/HITL)
- `999a88df-6ea4-4d06-9625-98e24dddf96d.ulg`: simulation build (SITL/HITL)
- `4b735bce-34a3-490d-b3a5-13811e5ff8c6.ulg`: simulation build (SITL/HITL)
- `5e105ea7-4ded-4a34-bdeb-7c1ac643bcfc.ulg`: simulation build (SITL/HITL)
- `fbbec1fe-adff-4eec-96be-eb4f1af30366.ulg`: simulation build (SITL/HITL)
- `15ce6e15-c49c-4a3e-b259-304b037ea52e.ulg`: simulation build (SITL/HITL)
- `3f96796a-0d64-40ce-942e-709eed4fa8a9.ulg`: simulation build (SITL/HITL)
- `164765f1-28ff-460b-bc45-1e53a7154cce.ulg`: simulation build (SITL/HITL)
- `63863e7a-b81c-45be-8b20-2ff17960782b.ulg`: simulation build (SITL/HITL)
- `3a536f9d-09be-4e7d-888e-2e8d2e93e941.ulg`: simulation build (SITL/HITL)
- `6c90ceb9-7f59-423d-864f-df3a4c2fdfdb.ulg`: simulation build (SITL/HITL)
- `51c41177-e55e-4bdd-bc53-ec864fc21b62.ulg`: simulation build (SITL/HITL)

## Airborne alarm / exceedance rates (production thresholds, no tuning)

| Metric | Sim reference | Real: `px4_telemetry` | Real: `independent_sensors` | Real: `independent_sensors_biascorr` |
|---|---|---|---|---|
| Usable flights | 12 | 0 | 0 | 0 |
| Airborne hours | 0.35 | 0.00 | 0.00 | 0.00 |
| physics_trigger_rate | 0.00 % (flights: 0) | — | — | — |
| ml_probe_alarm_rate | 0.30 % (flights: 9) | — | — | — |
| ml_probe_lone_threat_rate | 0.08 % (flights: 4) | — | — | — |
| exceed_pos_residual_m | 0.00 % (flights: 0) | — | — | — |
| exceed_gps_vfr_speed_diff_ms | 0.00 % (flights: 0) | — | — | — |
| exceed_gps_baro_alt_diff_m | 0.00 % (flights: 0) | — | — | — |
| exceed_alt_rate_ms | 0.05 % (flights: 3) | — | — | — |
| exceed_accel_ms2 | 0.00 % (flights: 0) | — | — | — |
| exceed_yaw_course_diff_deg | 0.00 % (flights: 0) | — | — | — |

## Feature distributions (airborne, pooled): p50 / p99

| Feature | Sim | `px4_telemetry` | `independent_sensors` | `independent_sensors_biascorr` | KS vs sim (px4_telemetry, independent_sensors, independent_sensors_biascorr) |
|---|---|---|---|---|---|
| pos_residual_m | 1.15 / 3.05 | — | — | — | —, —, — |
| gps_vfr_speed_diff_ms | 0.15 / 0.59 | — | — | — | —, —, — |
| gps_baro_alt_diff_m | 1.10 / 4.46 | — | — | — | —, —, — |
| alt_rate_ms | -0.04 / 15.95 | — | — | — | —, —, — |
| accel_ms2 | 1.65 / 9.29 | — | — | — | —, —, — |
| yaw_course_diff_deg | 0.35 / 3.22 | — | — | — | —, —, — |
| ml_nav_probe | 0.04 / 0.36 | — | — | — | —, —, — |

_Thresholds: {"pos_residual_m": 12.0, "gps_vfr_speed_diff_ms": 5.0, "gps_baro_alt_diff_m": 8.0, "alt_rate_ms": 25.0, "accel_ms2": 20.0, "yaw_course_diff_deg": 25.0, "ml_score_threshold": 0.62, "ml_lone_threat_threshold": 0.9563}_
