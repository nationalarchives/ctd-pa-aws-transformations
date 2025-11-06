import os
import json
import yaml
from dotenv import load_dotenv

class UniversalConfig:
    def __init__(self, env_file=".env", yaml_file=None, json_file=None):
        load_dotenv(env_file)
        self.yaml_config = self._load_yaml(yaml_file) if yaml_file else {}
        self.json_config = self._load_json(json_file) if json_file else {}

    def _load_yaml(self, file):
        with open(file) as f:
            return yaml.safe_load(f)

    def _load_json(self, file):
        with open(file) as f:
            return json.load(f)

    def get(self, key_path, default=None):
        # Check ENV first
        val = os.getenv(key_path)
        if val:
            return val

        # Check YAML nested keys
        if "." in key_path:
            keys = key_path.split(".")
            value = self.yaml_config
            for k in keys:
                value = value.get(k, {})
            if value != {}:
                return value

        # Check JSON
        if key_path in self.json_config:
            return self.json_config[key_path]

        return default