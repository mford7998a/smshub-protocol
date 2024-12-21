import requests
import json
import logging
import time
from typing import Dict, List, Optional, Union
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SmsHubConfig:
    api_key: str
    agent_id: str  # Your agent ID from SMS Hub
    server_url: str  # Your server's public URL that SMS Hub will call
    api_url: str = "https://agent.unerio.com/agent/api/sms"  # Updated to correct endpoint

class SmsHubAPI:
    def __init__(self, config: SmsHubConfig):
        self.config = config
        self.active_orders: Dict[str, Dict] = {}
        self.headers = {
            'User-Agent': 'SMSHubAgent/1.0',  # Required by protocol
            'Content-Type': 'application/json',
            'Accept-Encoding': 'gzip'  # Required by protocol
        }

    def _make_request(self, action: str, params: Dict) -> Optional[Dict]:
        """Make request to SMS Hub API."""
        try:
            # Format parameters according to SMS Hub documentation
            request_data = {
                'key': self.config.api_key,
                'action': action,
                **params
            }
            
            logger.info(f"Making request to SMS Hub: {action}")
            logger.debug(f"Request data: {request_data}")
            
            response = requests.post(
                self.config.api_url,
                json=request_data,
                headers=self.headers
            )
            response.raise_for_status()
            
            content = response.json()
            logger.info(f"SMS Hub Response: {content}")
            
            if content.get('status') == 'ERROR':
                logger.error(f"API Error: {content.get('error')}")
                return None
                
            return content
                
        except Exception as e:
            logger.error(f"API request failed: {e}")
            return None

    def push_sms(self, sms_id: int, phone: str, phone_from: str, text: str) -> bool:
        """Send SMS to SMSHUB server."""
        try:
            # No cleaning or modification of inputs - use exactly as provided
            data = {
                "smsId": sms_id,
                "phoneFrom": phone_from,
                "phone": phone,
                "text": text,
                "action": "PUSH_SMS",
                "key": self.config.api_key
            }
            
            logger.info(f"Sending SMS to SMS Hub")
            logger.info(f"Request data: {json.dumps(data)}")
            
            response = requests.post(
                self.config.api_url,
                json=data,
                headers=self.headers,
                timeout=30,
                verify=True
            )
            
            logger.info(f"Response status code: {response.status_code}")
            logger.info(f"Response content: {response.text}")
            
            try:
                result = response.json()
                if result.get('status') == 'SUCCESS':
                    return True
                return False
            except:
                return False
                
        except Exception as e:
            logger.error(f"Error in push_sms: {e}")
            return False