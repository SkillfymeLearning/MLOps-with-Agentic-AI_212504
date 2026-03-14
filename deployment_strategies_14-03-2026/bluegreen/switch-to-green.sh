#!/bin/bash
# Switch traffic from blue to green (promote new version)

kubectl patch service digits-server -n kubeflow \
  -p '{"spec":{"selector":{"version":"green"}}}'

echo "Traffic switched to GREEN (v2)"
