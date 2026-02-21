FROM python:3.11-slim

# Install DVC and any other dependencies you need
RUN pip install dvc[all] apache-airflow mlflow scikit-learn pandas numpy pyyaml

# Set working directory
WORKDIR /workspace

COPY . /workspace

# Default command (can be overridden by Airflow)
CMD ["bash"]
