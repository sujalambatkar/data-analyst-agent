FROM python:3.11-slim

RUN pip install --no-cache-dir pandas plotly matplotlib scipy numpy scikit-learn

WORKDIR /workspace

CMD ["python", "-c", "import sys, json; payload = json.loads(sys.stdin.read()); exec(payload['code'])"]
