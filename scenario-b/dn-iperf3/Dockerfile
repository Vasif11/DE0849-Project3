# N6 data-network endpoint: iperf3 server + return route to the UE address pool through the UPF.
FROM alpine:3.20
RUN apk add --no-cache iperf3 iproute2
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 5201
ENTRYPOINT ["/entrypoint.sh"]
