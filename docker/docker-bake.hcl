# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# The images the Docker smoke workflows build (#19527). One definition, read by
# .github/actions/build-smoke-images for docker-smoke-test.yml,
# hardened-smoke-test.yml and co-located-smoke.yml, which each carried their own
# copy of the same three `docker buildx build` calls.
#
# `docker buildx bake <group>` builds a group's targets concurrently in one
# BuildKit session, so the frontend and SLM builds run alongside the backend's
# dependency install instead of after it, and stages two Dockerfiles share are
# built once.
#
# Each target exports its layer cache to its OWN directory. The three builds used
# to share one --cache-to destination; every export replaced that directory's
# cache index, so only the last image's cache survived and the backend re-ran its
# dependency install on every run even when the exact cache key was restored.
#
# mode=min, not max: max also exports every intermediate stage and exhausted the
# runner's disk (see the cache rotation in the action).

variable "CACHE_DIR" {
  default = "/tmp/.buildx-cache"
}

variable "CACHE_DIR_NEW" {
  default = "/tmp/.buildx-cache-new"
}

function "cache_from" {
  params = [name]
  result = ["type=local,src=${CACHE_DIR}/${name}"]
}

function "cache_to" {
  params = [name]
  result = ["type=local,dest=${CACHE_DIR_NEW}/${name},mode=min"]
}

group "smoke" {
  targets = ["backend", "slm", "frontend"]
}

# The hardened run also starts the SLM-only GUI under the slm profile (#18585).
group "hardened" {
  targets = ["backend", "slm", "frontend", "slm-gui"]
}

target "backend" {
  context    = "."
  dockerfile = "docker/backend/Dockerfile"
  tags       = ["autobot/backend:latest"]
  cache-from = cache_from("backend")
  cache-to   = cache_to("backend")
}

target "slm" {
  context    = "."
  dockerfile = "docker/slm/Dockerfile"
  tags       = ["autobot/slm:latest"]
  cache-from = cache_from("slm")
  cache-to   = cache_to("slm")
}

target "frontend" {
  context    = "."
  dockerfile = "docker/frontend/Dockerfile"
  tags       = ["autobot/frontend:latest"]
  cache-from = cache_from("frontend")
  cache-to   = cache_to("frontend")
}

target "slm-gui" {
  context    = "."
  dockerfile = "docker/frontend/Dockerfile"
  target     = "slm-gui"
  tags       = ["autobot/slm-gui:latest"]
  cache-from = cache_from("slm-gui")
  cache-to   = cache_to("slm-gui")
}
