FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

ARG TELEGRAM_TOKEN
ARG ANTHROPIC_API_KEY
ENV TELEGRAM_TOKEN=$TELEGRAM_TOKEN
ENV ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY

CMD ["python", "bot.py"]
