import requests
import logging
import time
import json
from typing import Dict, Any

logger = logging.getLogger(__name__)

class SmsHubIntegration:
    def __init__(self, base_url: str = 'https://agent.unerio.com/agent/api/sms', api_key: str = None):
        self.base_url = base_url
        self.api_key = "15431U1ea5e5b53572512438b03fbe8f96fa10"  # Hardcoded API key
        self.retry_delay = 10  # seconds
        self.max_retries = 3
        self.headers = {
            'User-Agent': 'SMSHubAgent/1.0',  # Required by protocol
            'Content-Type': 'application/json',
            'Accept-Encoding': 'gzip'  # Required by protocol
        }
        
    def push_sms(self, sms_id: int, phone: int, phone_from: str, text: str) -> bool:
        """Push SMS to SMS Hub."""
        url = "https://agent.unerio.com/agent/api/sms"
        
        data = {
            "smsId": sms_id,
            "phoneFrom": phone_from,
            "phone": phone,
            "text": text,
            "action": "PUSH_SMS",
            "key": self.api_key
        }
        
        logger.info("=" * 80)
        logger.info("SMSHUB REQUEST: PUSH_SMS")
        logger.info(f"URL: {url}")
        logger.info(f"Headers: {json.dumps(self.headers, indent=2)}")
        logger.info(f"Request Data: {json.dumps(data, indent=2)}")
        logger.info("-" * 80)
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(url, json=data, headers=self.headers)
                
                logger.info("SMSHUB RESPONSE:")
                logger.info(f"Status Code: {response.status_code}")
                logger.info(f"Raw Response: {response.text}")
                
                result = response.json()
                logger.info(f"Parsed Response: {json.dumps(result, indent=2)}")
                logger.info("=" * 80)
                
                if result.get('status') == 'SUCCESS':
                    logger.info("SMS successfully pushed to SMSHUB")
                    return True
                    
                logger.error(f"SMSHUB Error: {result.get('error')}")
                
                if attempt < self.max_retries - 1:  # Don't sleep on last attempt
                    logger.info(f"Retrying in {self.retry_delay} seconds... (Attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(self.retry_delay)
                    
            except Exception as e:
                logger.error(f"Error pushing SMS to SMSHUB: {str(e)}")
                if attempt < self.max_retries - 1:  # Don't sleep on last attempt
                    logger.info(f"Retrying in {self.retry_delay} seconds... (Attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(self.retry_delay)
                    
        logger.error("Failed to push SMS after all retry attempts")
        return False