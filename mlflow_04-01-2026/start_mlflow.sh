export OIDC_PROVIDER_DISPLAY_NAME="Okta"
export OIDC_DISCOVERY_URL=https://integrator-2934168.okta.com/oauth2/default/.well-known/openid-configuration
export OIDC_ISSUER_URL=https://integrator-2934168.okta.com/oauth2/default
export OIDC_USERNAME_CLAIM='email'
export OIDC_CLIENT_ID=0oawwkg2jrUScvMwD697
export OIDC_SCOPE='openid profile email'
export OIDC_GROUPS_ATTRIBUTE='groups'
export OIDC_GROUP_NAME='User'
export OIDC_REDIRECT_URI='http://localhost:8080/callback'
export OIDC_CLIENT_SECRET=gPNxdQqP7XX4O8Jgp1KucDPHvPjaIxfqV58YjqsBoskXSmZclJkzdDifJb13Uemt
export OIDC_USER_GROUP="Everyone"
export MLFLOW_FLASK_SERVER_SECRET_KEY='446JqHgMB59jd80MQiWYoRsrH7J24pS6RH1piIfCPWA='
export MLFLOW_AUTH_CONFIG_PATH=$PWD/basic_auth.ini
export MLFLOW_TRACKING_USERNAME=admin
export MLFLOW_TRACKING_PASSWORD=password
mlflow server --app-name oidc-auth --host 0.0.0.0 --port 8080