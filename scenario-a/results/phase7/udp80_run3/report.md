# Experiment udp80_run3

- protocol: **UDP**, offered load: **80 Mbit/s**, duration 10 s, observation interval (snapshot midpoints): 10.4 s

## iperf3 receiver-side result

| metric | value |
|---|---|
| receiver_mbps | 79.93 |
| jitter_ms | 0.019 |
| lost_packets | 0 |
| packets | 69069 |
| lost_percent | 0 |

## OpenFlow flow-counter deltas (reference path, rules matching dl_dst=h4)

| switch | in_port | out_port | Δpackets (path total) | Δbytes (path total) | Δpackets h1 rule only | other-ingress extra pkts | Δbytes/interval (Mbit/s) |
|---|---|---|---|---|---|---|---|
| s1 | 1 | 3 | 69084 | 102914282 | 69084 | 0 | 79.165 |
| s2 | 1 | 2 | 69084 | 102914282 | 69084 | 0 | 79.165 |
| s3 | 3 | 2 | 69084 | 102914282 | 69084 | 0 | 79.165 |

Flow counters identical across s1, s2, s3: **True** (packet spread 0, 0.0 %; snapshot re-reads until stable: {'before': 2, 'after': 3})

## Inter-switch port counters (tx at one end vs rx at the other)

| link | tx pkts | rx pkts | tx bytes | rx bytes | match |
|---|---|---|---|---|---|
| s1:3->s2:1 | 69084 | 69084 | 102914282 | 102914282 | True |
| s2:1->s1:3 | 14 | 14 | 1250 | 1250 | True |
| s2:2->s3:3 | 69084 | 69084 | 102914282 | 102914282 | True |
| s3:3->s2:2 | 14 | 14 | 1250 | 1250 | True |

All inter-switch counters match: **True**; port drops/errors per switch: {'s1': 0, 's2': 0, 's3': 0}

