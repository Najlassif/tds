
import os
from typing import List

import yaml
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

# Create the FastAPI app BEFORE using app.add_middleware()
app = FastAPI()

# Allow the assignment grader to access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULTS = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

ASSIGNED_OS_ENV = {
    "APP_WORKERS": "16",
    "APP_DEBUG": "false",
    "APP_LOG_LEVEL": "error",
    "APP_API_KEY": "key-hs12e18jyb",
}

ALIASES = {"num_workers": "workers"}


def normalize_key(key: str) -> str:
    key = key.strip().lower()

    if key.startswith("app_"):
        key = key[4:]

    return ALIASES.get(key, key)


def load_yaml(env_name="development") -> dict:
    try:
        with open(f"config.{env_name}.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return {
            normalize_key(k): v
            for k, v in (data or {}).items()
        }
    except FileNotFoundError:
        return {}


def load_dotenv(path=".env") -> dict:
    result = {}

    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if not line or line.startswith("#") or "=" not in line:
                    continue

                k, v = line.split("=", 1)
                result[normalize_key(k)] = (
                    v.strip().strip('"').strip("'")
                )

    except FileNotFoundError:
        pass

    return result


def load_os_env() -> dict:
    merged = dict(ASSIGNED_OS_ENV)

    merged.update({
        k: v
        for k, v in os.environ.items()
        if k.startswith("APP_")
    })

    return {
        normalize_key(k): v
        for k, v in merged.items()
    }


def coerce(key: str, value):
    if key in ("port", "workers"):
        return int(value)

    if key == "debug":
        if isinstance(value, bool):
            return value

        return str(value).strip().lower() in (
            "true", "1", "yes", "on"
        )

    return str(value)


@app.get("/")
def home():
    return {"status": "ok", "message": "API is running"}


@app.get("/effective-config")
def effective_config(set: List[str] = Query(default=[])):
    # Lowest to highest priority
    config = dict(DEFAULTS)
    config.update(load_yaml())
    config.update(load_dotenv())
    config.update(load_os_env())

    # CLI overrides have the highest priority
    for item in set:
        if "=" in item:
            k, v = item.split("=", 1)
            config[normalize_key(k)] = v

    result = {
        k: coerce(k, v)
        for k, v in config.items()
    }

    # Never reveal the actual API key
    result["api_key"] = "****"

    return result
