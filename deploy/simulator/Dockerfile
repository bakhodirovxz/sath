# Sath GES simulyatori + gateway (sinov stendi): Modbus TCP 5020, OPC UA 4840, IEC 104 2404 (c104 — GPLv3, server obraziga kirmaydi). Kontekst: repo ildizi.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY sim/ ./sim/
RUN pip install --no-cache-dir ./sim "pymodbus>=3.8,<3.10" "asyncua>=1.1" requests c104
COPY deploy/simulator/ges_simulator.py deploy/gateway/ges_gateway.py ./
# Root siz (OPS-02); gateway spool/konfiguratsiyasi /tmp da (compose: read_only + tmpfs)
RUN useradd --system --uid 10001 --no-create-home sath
USER sath
EXPOSE 5020 4840 2404
CMD ["python", "ges_simulator.py", "--scenario", "normal", "--modbus", "0.0.0.0:5020", "--opcua", "opc.tcp://0.0.0.0:4840/sath-sim/", "--iec104", "0.0.0.0:2404"]
