#FROM means you have a base image
FROM python:3.10-slim 
RUN pip install mlflow numpy scipy pandas scikit-learn cloudpickle boto3

COPY train.py .
COPY mlflow.py .
COPY matrix.png .
COPY wine-quality.csv .