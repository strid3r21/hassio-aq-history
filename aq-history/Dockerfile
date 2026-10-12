FROM python:3.12-slim
RUN pip install --no-cache-dir "pymysql>=1.1"
WORKDIR /app
COPY app.py /app/app.py
EXPOSE 8799
CMD ["python", "/app/app.py"]
