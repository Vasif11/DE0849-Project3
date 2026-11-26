#!/usr/bin/env python3
r"""Scenario A reference topology (3 x OVS, 4 hosts, linear), external OS-Ken controller.

    h1 --\                                   /-- h3
          s1 ------------ s2 ------------ s3
    h2 --/                                   \-- h4

* hosts  : h1..h4 = 10.0.0.1..10.0.0.4/24
* DPIDs  : s1=0000000000000001, s2=...02, s3=...03
* links  : Mininet TCLink, 100 Mbit/s, 1 ms delay, 0 % loss, 1000-packet queue,
           bandwidth shaped by TBF (use_tbf) with a netem child for delay/loss/queue.
* switch : OVS, OpenFlow 1.3, fail-mode secure (no silent fallback to standalone switching)

Links are created in a fixed order so the port numbers match the reference path
h1-s1-s2-s3-h4:  s1: h1=1 h2=2 s2=3 | s2: s1=1 s3=2 | s3: h3=1 h4=2 s2=3
"""
import argparse
import sys

from mininet.link import TCLink
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController

CONTROLLER_IP = "127.0.0.1"
CONTROLLER_PORT = 6633
LINK_OPTS = dict(bw=100, delay="1ms", loss=0, max_queue_size=1000, use_tbf=True)


def build_net(controller_ip=CONTROLLER_IP, controller_port=CONTROLLER_PORT, link_opts=None):
    opts = dict(LINK_OPTS if link_opts is None else link_opts)
    net = Mininet(
        switch=OVSSwitch,
        link=TCLink,
        controller=None,
        autoSetMacs=True,
        autoStaticArp=False,
        waitConnected=False,
    )
    net.addController("c0", controller=RemoteController, ip=controller_ip, port=controller_port,
                      protocols="OpenFlow13")
    sw_kw = dict(protocols="OpenFlow13", failMode="secure")
    s1 = net.addSwitch("s1", dpid="0000000000000001", **sw_kw)
    s2 = net.addSwitch("s2", dpid="0000000000000002", **sw_kw)
    s3 = net.addSwitch("s3", dpid="0000000000000003", **sw_kw)
    h1 = net.addHost("h1", ip="10.0.0.1/24")
    h2 = net.addHost("h2", ip="10.0.0.2/24")
    h3 = net.addHost("h3", ip="10.0.0.3/24")
    h4 = net.addHost("h4", ip="10.0.0.4/24")
    # order matters (port numbers), see module docstring
    for a, b in [(h1, s1), (h2, s1), (h3, s3), (h4, s3), (s1, s2), (s2, s3)]:
        net.addLink(a, b, **opts)
    return net


def start_net(net, wait_s=20):
    """Start the network, silence IPv6 (its multicast would pollute the OpenFlow evidence)
    and wait until all three switches report an active controller session."""
    import subprocess
    import time
    net.start()
    for h in net.hosts:
        h.cmd("sysctl -qw net.ipv6.conf.all.disable_ipv6=1 net.ipv6.conf.default.disable_ipv6=1")
    for sw in net.switches:
        for intf in sw.intfList():
            if intf.name != "lo":
                subprocess.run(f"sysctl -qw net.ipv6.conf.{intf.name}.disable_ipv6=1",
                               shell=True, capture_output=True)
    deadline = time.time() + wait_s
    while time.time() < deadline:
        out = subprocess.run("ovs-vsctl --bare --columns=is_connected find controller",
                             shell=True, capture_output=True, text=True).stdout.split()
        if len(out) >= 3 and all(x == "true" for x in out):
            return True
        time.sleep(1)
    return False


def warm_up(net, tries=4):
    """Establish stable MAC-learning state on ALL switches (Phase 8 precondition).

    A reactive learning switch only learns from packet-ins. Replies that match an already installed
    rule never reach the controller, so a host can stay unknown on a switch (observed: h4 unknown at
    s1/s2, every h1->h4 packet then floods through the controller). Flushing the ARP caches makes
    every host re-announce itself with a broadcast ARP request, which is never matched by a
    unicast rule and therefore reaches the controller on every switch.
    Returns True when s1/s2/s3 hold the learned forwarding rules for the reference path both ways.
    """
    import subprocess
    import time

    def flows(sw):
        return subprocess.run(f"ovs-ofctl -O OpenFlow13 dump-flows {sw}", shell=True,
                              capture_output=True, text=True).stdout

    for _ in range(tries):
        for h in net.hosts:
            h.cmd("ip neigh flush all")
        # Linux learns a neighbour from a received ARP *request*, so e.g. h4 may never need to
        # broadcast. Make every host announce itself with an Ethernet-broadcast frame (broadcast
        # ping): it floods to every switch as a packet-in, so every switch learns every host.
        for h in net.hosts:
            h.cmd("ping -b -c 1 -W 1 10.0.0.255 >/dev/null 2>&1")
            time.sleep(0.15)
        net.pingAll()
        net.get("h1").cmd("ping -c 2 -W 1 10.0.0.4")
        net.get("h4").cmd("ping -c 2 -W 1 10.0.0.1")
        time.sleep(0.5)
        ok = ("in_port=1,dl_dst=00:00:00:00:00:04" in flows("s1")
              and "in_port=3,dl_dst=00:00:00:00:00:01" in flows("s1")
              and "in_port=1,dl_dst=00:00:00:00:00:04" in flows("s2")
              and "in_port=2,dl_dst=00:00:00:00:00:01" in flows("s2")
              and "in_port=3,dl_dst=00:00:00:00:00:04" in flows("s3")
              and "in_port=2,dl_dst=00:00:00:00:00:01" in flows("s3"))
        if ok:
            return True
    return False


def port_map(net):
    """{switch: {port_no: neighbour_name}} read from the live topology."""
    out = {}
    for sw in net.switches:
        out[sw.name] = {}
        for intf in sw.intfList():
            if intf.name == "lo":
                continue
            link = intf.link
            if link is None:
                continue
            other = link.intf2 if link.intf1 == intf else link.intf1
            out[sw.name][sw.ports[intf]] = other.node.name
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="start the Scenario A topology with the Mininet CLI")
    ap.add_argument("--controller-ip", default=CONTROLLER_IP)
    ap.add_argument("--controller-port", type=int, default=CONTROLLER_PORT)
    a = ap.parse_args()
    setLogLevel("info")
    from mininet.cli import CLI
    n = build_net(a.controller_ip, a.controller_port)
    n.start()
    CLI(n)
    n.stop()
    sys.exit(0)
