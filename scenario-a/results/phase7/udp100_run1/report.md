# Experiment udp100_run1

- protocol: **UDP**, offered load: **100 Mbit/s**, duration 10 s, observation interval (snapshot midpoints): 10.52 s

## iperf3 receiver-side result

| metric | value |
|---|---|
| receiver_mbps | 97.1 |
| jitter_ms | 0.022 |
| lost_packets | 1437 |
| packets | 86335 |
| lost_percent | 1.6644 |

## OpenFlow flow-counter deltas (reference path, rules matching dl_dst=h4)

| switch | in_port | out_port | Δpackets (path total) | Δbytes (path total) | Δpackets h1 rule only | other-ingress extra pkts | Δbytes/interval (Mbit/s) |
|---|---|---|---|---|---|---|---|
| s1 | 1 | 3 | 84913 | 126499495 | 84913 | 0 | 96.197 |
| s2 | 1 | 2 | 84913 | 126499495 | 84913 | 0 | 96.197 |
| s3 | 3 | 2 | 84913 | 126499495 | 84913 | 0 | 96.197 |

Flow counters identical across s1, s2, s3: **True** (packet spread 0, 0.0 %; snapshot re-reads until stable: {'before': 2, 'after': 3})

## Inter-switch port counters (tx at one end vs rx at the other)

| link | tx pkts | rx pkts | tx bytes | rx bytes | match |
|---|---|---|---|---|---|
| s1:3->s2:1 | 84913 | 84913 | 126499495 | 126499495 | True |
| s2:1->s1:3 | 14 | 14 | 1250 | 1250 | True |
| s2:2->s3:3 | 84913 | 84913 | 126499495 | 126499495 | True |
| s3:3->s2:2 | 14 | 14 | 1250 | 1250 | True |

All inter-switch counters match: **True**; port drops/errors per switch: {'s1': 0, 's2': 0, 's3': 0}

