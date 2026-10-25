"""Shared pipeline identity; deployments supply the Git revision explicitly."""

import os

PIPELINE_VERSION = "0.2.1"
GIT_SHA = os.environ.get("GIT_SHA", "dev")
