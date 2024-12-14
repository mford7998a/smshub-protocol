"""Configuration settings for the application."""

import json
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Default API settings
SMSHUB_API_KEY = "15431U1ea5e5b53572512438b03fbe8f96fa10"  # Keep the full API key including U prefix
SMSHUB_AGENT_ID = "15431"  # This can be overridden in config.json
SMSHUB_SERVER_URL = "https://smshub.org/stubs/handler_api.php"  # Default API endpoint

class Config:
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.config: Dict[str, Any] = self._load_config()
        
        # Update global constants from config
        global SMSHUB_API_KEY, SMSHUB_AGENT_ID, SMSHUB_SERVER_URL
        SMSHUB_API_KEY = self.config.get('smshub_api_key', SMSHUB_API_KEY)
        SMSHUB_AGENT_ID = self.config.get('smshub_agent_id', SMSHUB_AGENT_ID)
        SMSHUB_SERVER_URL = self.config.get('smshub_server_url', SMSHUB_SERVER_URL)

        # Set logging level based on debug mode
        log_level = logging.DEBUG if self.config.get('debug_mode', False) else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(levelname)s: %(message)s'
        )
        logger.info(f"Logging level set to: {'DEBUG' if log_level == logging.DEBUG else 'INFO'}")

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        default_config = {
            "server_port": 5000,
            "tunnel": {
                "enabled": True,
                "type": "localtonet",
                "name": "smshub-agent"
            },
            "services": {
                "lf": True,
                "tu": True,
                "vi": True,
                "wa": True,
                "mm": True,
                "aba": True,
                "abb": True,
                "abn": True,
                "ac": True,
                "acb": True,
                "acc": True,
                "acz": True,
                "ada": True,
                "aea": True,
                "aeu": True,
                "aez": True,
                "afk": True,
                "aft": True,
                "afz": True,
                "agk": True,
                "agm": True,
                "agy": True,
                "ahe": True,
                "aho": True,
                "ahv": True,
                "aig": True,
                "aim": True,
                "aiv": True,
                "aiw": True,
                "aiz": True,
                "aja": True,
                "ajj": True,
                "ak": True,
                "ako": True,
                "alq": True,
                "am": True,
                "ama": True,
                "amb": True,
                "amj": True,
                "aml": True,
                "an": True,
                "ane": True,
                "anj": True,
                "anp": True,
                "aob": True,
                "aoe": True,
                "aoi": True,
                "aoj": True,
                "aok": True,
                "aol": True,
                "aom": True,
                "aon": True,
                "aor": True,
                "aow": True,
                "apb": True,
                "ape": True,
                "apk": True,
                "apl": True,
                "apm": True,
                "app": True,
                "apr": True,
                "apt": True,
                "aqf": True,
                "aqg": True,
                "aqh": True,
                "aqt": True,
                "are": True,
                "arl": True,
                "arw": True,
                "asf": True,
                "asn": True,
                "asp": True,
                "asq": True,
                "atm": True,
                "atr": True,
                "atw": True,
                "atx": True,
                "atz": True,
                "aub": True,
                "auj": True,
                "aul": True,
                "aum": True,
                "auz": True,
                "ava": True,
                "avc": True,
                "bf": True,
                "bl": True,
                "bo": True,
                "bs": True,
                "bz": True,
                "ck": True,
                "cq": True,
                "dc": True,
                "dd": True,
                "dg": True,
                "dp": True,
                "dq": True,
                "dr": True,
                "ds": True,
                "ef": True,
                "ep": True,
                "et": True,
                "ew": True,
                "fb": True,
                "fu": True,
                "gf": True,
                "gm": True,
                "gp": True,
                "gq": True,
                "gr": True,
                "gt": True,
                "hb": True,
                "ho": True,
                "hw": True,
                "ig": True,
                "ij": True,
                "im": True,
                "iq": True,
                "it": True,
                "jg": True,
                "jq": True,
                "ka": True,
                "kc": True,
                "kf": True,
                "ki": True,
                "kt": True,
                "li": True,
                "lo": True,
                "ls": True,
                "lx": True,
                "ma": True,
                "mb": True,
                "mc": True,
                "me": True,
                "mj": True,
                "mo": True,
                "mt": True,
                "my": True,
                "nc": True,
                "nf": True,
                "nv": True,
                "nz": True,
                "oe": True,
                "oh": True,
                "ot": True,
                "oz": True,
                "pf": True,
                "pm": True,
                "qf": True,
                "qo": True,
                "qq": True,
                "qx": True,
                "rc": True,
                "re": True,
                "rl": True,
                "rm": True,
                "rt": True,
                "rz": True,
                "sf": True,
                "sn": True,
                "th": True,
                "ti": True,
                "tn": True,
                "tr": True,
                "ts": True,
                "tv": True,
                "tw": True,
                "tx": True,
                "ub": True,
                "uk": True,
                "un": True,
                "uz": True,
                "vm": True,
                "vp": True,
                "vz": True,
                "wb": True,
                "wc": True,
                "wg": True,
                "wr": True,
                "wx": True,
                "xv": True,
                "xz": True,
                "ya": True,
                "yl": True,
                "yw": True,
                "yy": True,
                "za": True,
                "zh": True,
                "zk": True,
                "zm": True,
                "zr": True,
                "zy": True
            },
            "service_prices": {
                # Default price for all services
                "default": 1.0
            },
            "smshub_api_key": SMSHUB_API_KEY,  # Add this
            "smshub_agent_id": SMSHUB_AGENT_ID,  # Add this
            "smshub_server_url": SMSHUB_SERVER_URL,  # Add this
            "auto_start_server": True,
            "debug_mode": False,  # Default to INFO level logging
            "scan_interval": 10,  # Modem scan interval in seconds
        }

        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    saved_config = json.load(f)
                    # Update default config with saved values
                    default_config.update(saved_config)
                    logger.info("Configuration loaded successfully")
            else:
                self.save_config(default_config)
                logger.info("Created new configuration file with defaults")
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")

        return default_config

    def save_config(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Save configuration to file."""
        if config is not None:
            self.config = config

        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
            logger.info("Configuration saved successfully")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value and save."""
        self.config[key] = value
        self.save_config()

    def update(self, updates: Dict[str, Any]) -> None:
        """Update multiple configuration values and save."""
        self.config.update(updates)
        self.save_config()

# Create global config instance
config = Config()