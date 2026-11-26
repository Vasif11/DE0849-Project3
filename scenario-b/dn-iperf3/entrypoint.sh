#!/bin/sh
# Replies to the UE (10.45.0.0/16) must re-enter the 5G user plane through the UPF (10.20.6.14 on N6).
UE_POOL="${UE_POOL:-10.45.0.0/16}"
UPF_N6="${UPF_N6:-10.20.6.14}"
ip route replace "$UE_POOL" via "$UPF_N6" && echo "[dn] route $UE_POOL via $UPF_N6"
exec iperf3 -s
