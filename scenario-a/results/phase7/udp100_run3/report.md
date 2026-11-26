# Experiment udp100_run3

- protocol: **UDP**, offered load: **100 Mbit/s**, duration 10 s, observation interval (snapshot midpoints): 10.515 s

## iperf3 receiver-side result

| metric | value |
|---|---|
| receiver_mbps | 97.11 |
| jitter_ms | 0.0333 |
| lost_packets | 1435 |
| packets | 86336 |
| lost_percent | 1.6621 |

## OpenFlow flow-counter deltas (reference path, rules matching dl_dst=h4)

| switch | in_port | out_port | Δpackets (path total) | Δbytes (path total) | Δpackets h1 rule only | other-ingress extra pkts | Δbytes/interval (Mbit/s) |
|---|---|---|---|---|---|---|---|
| s1 | 1 | 3 | 84916 | 126503961 | 84916 | 0 | 96.246 |
| s2 | 1 | 2 | 84916 | 126503961 | 84916 | 0 | 96.246 |
| s3 | 3 | 2 | 84916 | 126503961 | 84916 | 0 | 96.246 |

Flow counters identical across s1, s2, s3: **True** (packet spread 0, 0.0 %; snapshot re-reads until stable: {'before': 2, 'after': 3})

## Inter-switch port counters (tx at one end vs rx at the other)

| link | tx pkts | rx pkts | tx bytes | rx bytes | match |
|---|---|---|---|---|---|
| s1:3->s2:1 | 84916 | 84916 | 126503961 | 126503961 | True |
| s2:1->s1:3 | 14 | 14 | 1253 | 1253 | True |
| s2:2->s3:3 | 84916 | 84916 | 126503961 | 126503961 | True |
| s3:3->s2:2 | 14 | 14 | 1253 | 1253 | True |

All inter-switch counters match: **True**; port drops/errors per switch: {'s1': 0, 's2': 0, 's3': 0}

