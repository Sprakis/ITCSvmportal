FROM python:3.12.3

WORKDIR /bot/
COPY requiriments.txt ./
RUN pip3 install --no-cache-dir -r requiriments.txt

CMD ["/bin/bash", "-c", "python3.12 bot.py"]