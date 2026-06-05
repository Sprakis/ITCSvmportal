FROM python:3.12.3

WORKDIR /app/
COPY ./requiriments.txt ./
RUN pip3 install --no-cache-dir -r requiriments.txt

CMD ["/bin/bash", "-c", "python3.12 app.py"]