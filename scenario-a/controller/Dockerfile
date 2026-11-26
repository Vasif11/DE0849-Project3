# Scenario A external SDN controller image: telecom-lab-osken:1.0 (OS-Ken 3.1.1)
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir os-ken==3.1.1

WORKDIR /app
ENV PYTHONPATH=/app
COPY learning_switch.py classifier_policy.py /app/

# OpenFlow listens on TCP 6633 (host networking is set in docker-compose / docker run)
EXPOSE 6633
CMD ["osken-manager", "--ofp-tcp-listen-port", "6633", "--verbose", "/app/learning_switch.py"]
