FROM python:3.10-slim

RUN pip install mlflow numpy scipy pandas scikit-learn cloudpickle

COPY train.py .
COPY wine-quality.csv .