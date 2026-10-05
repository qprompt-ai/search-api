FROM python:3.12-alpine

COPY scrape.py /opt/scrape.py

ENTRYPOINT ["python3", "/opt/scrape.py"]
