# Scenario B Near-RT RIC image: telecom-lab-flexric:1.0
# FlexRIC (EURECOM) br-flexric branch, pinned commit; E2AP v2 / E2SM-KPM v3.00 / E2SM-RC;
# C xApps built (xapp_oran_moni = the reference KPM monitoring xApp). No xApp DB, no Python SWIG layer.
FROM ubuntu:22.04
ARG DEBIAN_FRONTEND=noninteractive
ARG FLEXRIC_COMMIT=736508123fe4b5dc3db83fb5baf5f0a8e9b04fe8

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential cmake git ca-certificates pkg-config libsctp-dev libpcre2-dev python3 python3-dev \
      libconfig-dev libconfig++-dev libssl-dev libpthread-stubs0-dev bison flex gcc-12 g++-12 \
      iproute2 iputils-ping netcat-openbsd tcpdump \
    && rm -rf /var/lib/apt/lists/*

# gcc-11 (Ubuntu 22.04 default) hits an internal compiler error (segfault in cc1) on FlexRIC's
# _Generic decoder macros; gcc-12 builds it correctly.
ENV CC=gcc-12 CXX=g++-12

WORKDIR /opt
RUN git clone https://gitlab.eurecom.fr/mosaic5g/flexric.git flexric \
 && cd flexric && git checkout ${FLEXRIC_COMMIT}

WORKDIR /opt/flexric/build
# Only KPM and RC service models are needed (OCUDU E2 agent exposes exactly these). Dropping the
# MAC/RLC/PDCP/SLICE/TC/GTP SMs also keeps the build within the 4 GB lab host (-j1: the ASN.1
# generated sources made cc1 crash with an internal compiler error at -j2).
RUN cmake -DKPM_VERSION=KPM_V3_00 -DE2AP_VERSION=E2AP_V2 -DXAPP_DB=NONE_XAPP \
          -DXAPP_MULTILANGUAGE=OFF -DUNIT_TEST=OFF -DEMU_AGENT=OFF \
          -DSM_MAC=OFF -DSM_RLC=OFF -DSM_PDCP=OFF -DSM_SLICE=OFF -DSM_TC=OFF -DSM_GTP=OFF .. \
 && make -j1 \
 && make install

# service-model libraries are installed to /usr/local/lib/flexric ; RIC/xApp config to /usr/local/etc/flexric
ENV LD_LIBRARY_PATH=/usr/local/lib/flexric:/usr/local/lib
WORKDIR /opt/flexric
CMD ["/bin/bash"]
