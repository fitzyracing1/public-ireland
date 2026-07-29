FROM python:3.12-slim
WORKDIR /app
COPY mock_server.py .
COPY data/ ./data/
EXPOSE 3004
CMD ["python", "mock_server.py", "--port", "3004"]
