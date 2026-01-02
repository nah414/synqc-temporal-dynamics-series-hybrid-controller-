FROM python:3.11-slim

WORKDIR /app

# Copy the backend code
COPY synqc_shor_addon_v2/backend /app

# Install dependencies
RUN pip install --no-cache-dir \
    fastapi>=0.110 \
    pydantic>=2.0 \
    uvicorn[standard]>=0.27 \
    qiskit>=1.0 \
    qiskit-aer>=0.13 \
    qiskit-algorithms>=0.3

# Expose port
EXPOSE 8002

# Run the application
CMD ["uvicorn", "run_demo_app:app", "--host", "0.0.0.0", "--port", "8002"]
