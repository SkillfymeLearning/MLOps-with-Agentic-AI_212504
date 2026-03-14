#!/bin/bash
# Rollback: Switch traffic from green back to blue

kubectl patch service digits-server -n kubeflow \
  -p '{"spec":{"selector":{"version":"blue"}}}'

echo "Traffic switched to BLUE (v1) - Rollback complete"
