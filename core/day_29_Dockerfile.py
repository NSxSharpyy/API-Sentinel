# Step A: Ingest an optimized Python runtime infrastructure layer
FROM python:3.10-slim

# Step B: Set structural isolated workspace directory inside container sandbox
WORKDIR /app/behavioral_ai_engine

# Step C: Copy localized script asset elements into container perimeter bounds
COPY . /app/behavioral_ai_engine/

# Step D: Configure application metadata parameters routing variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Step E: Enforce safe non-root daemon execution privilege boundaries
RUN useradd -u 8852 security_engine_user && chown -R security_engine_user:security_engine_user /app
USER security_engine_user

# Step F: Expose standard security service metrics port limits
EXPOSE 8080

# Run automated validation diagnostic check runner directly upon deployment instantiation
CMD ["python", "day27_accuracy_benchmark.py"]
