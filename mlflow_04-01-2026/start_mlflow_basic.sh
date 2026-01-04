
export MLFLOW_FLASK_SERVER_SECRET_KEY='mysecret'
export MLFLOW_AUTH_CONFIG_PATH=$PWD/basic_auth.ini
# export MLFLOW_TRACKING_USERNAME=admin
# export MLFLOW_TRACKING_PASSWORD=password@1234
mlflow server --app-name basic-auth --host 0.0.0.0 --port 8080