# Experiment tcp_run1

- protocol: **TCP**, offered load: **None Mbit/s**, duration 10 s, observation interval (snapshot midpoints): 10.418 s

## iperf3 receiver-side result

| metric | value |
|---|---|
| receiver_mbps | 94.62 |
| sender_mbps | 102.43 |
| retransmits | 11 |

## OpenFlow flow-counter deltas (reference path, rules matching dl_dst=h4)

| switch | in_port | out_port | Δpackets (path total) | Δbytes (path total) | Δpackets h1 rule only | other-ingress extra pkts | Δbytes/interval (Mbit/s) |
|---|---|---|---|---|---|---|---|
| s1 | 1 | 3 | 26923 | 123498913 | 26923 | 0 | 94.835 |
| s2 | 1 | 2 | 26921 | 123472717 | 26921 | 0 | 94.815 |
| s3 | 3 | 2 | 26920 | 123459619 | 26920 | 0 | 94.805 |

Flow counters identical across s1, s2, s3: **False** (packet spread 3, 0.0111 %; snapshot re-reads until stable: {'before': 2, 'after': 2})

## Inter-switch port counters (tx at one end vs rx at the other)

| link | tx pkts | rx pkts | tx bytes | rx bytes | match |
|---|---|---|---|---|---|
| s1:3->s2:1 | 26965 | 26965 | 123948002 | 123948002 | True |
| s2:1->s1:3 | 17728 | 17728 | 1172299 | 1172299 | True |
| s2:2->s3:3 | 26965 | 26965 | 123948002 | 123948002 | True |
| s3:3->s2:2 | 17728 | 17728 | 1172299 | 1172299 | True |

All inter-switch counters match: **True**; port drops/errors per switch: {'s1': 0, 's2': 0, 's3': 0}

