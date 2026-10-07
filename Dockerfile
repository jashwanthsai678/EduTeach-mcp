FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core/ core/
COPY mcp_server/ mcp_server/

EXPOSE 8000

CMD ["python", "-m", "mcp_server.server"]
