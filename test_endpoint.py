import requests
import json
import logging
import time

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_get_services():
    url = "https://fzn84ln.localto.net/"  # Note the trailing slash
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SMSHubAgent/1.0",
        "Accept-Encoding": "gzip",
        "localtonet-skip-warning": "true"  # Added to bypass warning page
    }
    data = {
        "action": "GET_SERVICES",
        "key": "15431U1ea5e5b53572512438b03fbe8f96fa10"  # Exact key from screenshot
    }

    try:
        logger.info(f"Making request to {url}")
        logger.info(f"Headers: {headers}")
        logger.info(f"Data: {data}")
        
        response = requests.post(
            url,
            headers=headers,
            json=data,
            verify=False
        )
        
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")
        logger.info(f"Response content: {response.text}")
        
        response_data = response.json()
        
        # Verify response format
        assert 'countryList' in response_data, "Missing countryList in response"
        assert isinstance(response_data['countryList'], list), "countryList should be an array"
        
        # Print active modem counts
        for country in response_data['countryList']:
            for operator, services in country['operatorMap'].items():
                print(f"\nCountry: {country['country']}")
                print(f"Operator: {operator}")
                for service, count in services.items():
                    print(f"  {service}: {count} modems")
                    
        return response_data
    except Exception as e:
        logger.error(f"Error making request: {e}")
        return None

def test_get_number():
    """Test GET_NUMBER endpoint."""
    url = "https://fzn84ln.localto.net/"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SMSHubAgent/1.0",
        "Accept-Encoding": "gzip",
        "localtonet-skip-warning": "true"
    }
    data = {
        "action": "GET_NUMBER",
        "key": "1543IU7eA5e5b5357251243Bb03fbe8f96fa10",
        "country": "russia",
        "operator": "any",
        "service": "vk",
        "sum": 10.00,  # Price in rubles
        "currency": 643,  # 643 is the code for RUB
        "exceptionPhoneSet": []  # Optional list of phone numbers to exclude
    }

    try:
        logger.info(f"\nTesting GET_NUMBER endpoint")
        logger.info(f"Making request to {url}")
        logger.info(f"Headers: {headers}")
        logger.info(f"Data: {data}")
        
        response = requests.post(
            url,
            headers=headers,
            json=data,
            verify=False
        )
        
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")
        logger.info(f"Response content: {response.text}")
        
        response_data = response.json()
        print("\nGET_NUMBER Response:")
        print(json.dumps(response_data, indent=2))
        
        # Extract phone number if successful
        if response_data.get('status') == 'SUCCESS':
            return response_data.get('phone')
        return None
    except Exception as e:
        logger.error(f"Error making request: {e}")
        return None

def test_finish_activation(activation_id: int, status: int = 3):
    """Test FINISH_ACTIVATION endpoint.
    Status codes:
    1 - Do not provide for this service
    3 - Successfully sold
    4 - Cancelled
    5 - Refunded
    """
    url = "https://fzn84ln.localto.net/"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SMSHubAgent/1.0",
        "Accept-Encoding": "gzip",
        "localtonet-skip-warning": "true"
    }
    data = {
        "action": "FINISH_ACTIVATION",
        "key": "1543IU7eA5e5b5357251243Bb03fbe8f96fa10",
        "id": activation_id,
        "status": status
    }

    try:
        logger.info(f"\nTesting FINISH_ACTIVATION endpoint")
        logger.info(f"Making request to {url}")
        logger.info(f"Headers: {headers}")
        logger.info(f"Data: {data}")
        
        response = requests.post(
            url,
            headers=headers,
            json=data,
            verify=False
        )
        
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")
        logger.info(f"Response content: {response.text}")
        
        response_data = response.json()
        print("\nFINISH_ACTIVATION Response:")
        print(json.dumps(response_data, indent=2))
        return response_data
    except Exception as e:
        logger.error(f"Error making request: {e}")
        return None

def test_push_sms(phone: str = None, text: str = None):
    """Test PUSH_SMS endpoint.
    This simulates receiving an SMS and forwarding it to SMSHub.
    """
    if not phone or not text:
        phone = "+1234567890"  # Example phone number
        text = "Test SMS message"
    
    url = "https://fzn84ln.localto.net/"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SMSHubAgent/1.0",
        "Accept-Encoding": "gzip",
        "localtonet-skip-warning": "true"
    }
    data = {
        "action": "PUSH_SMS",
        "key": "1543IU7eA5e5b5357251243Bb03fbe8f96fa10",
        "phone": int(phone.replace("+", "").replace("-", "")),  # Clean number and convert to int
        "text": text
    }

    try:
        logger.info(f"\nTesting PUSH_SMS endpoint")
        logger.info(f"Making request to {url}")
        logger.info(f"Headers: {headers}")
        logger.info(f"Data: {data}")
        
        response = requests.post(
            url,
            headers=headers,
            json=data,
            verify=False
        )
        
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")
        logger.info(f"Response content: {response.text}")
        
        response_data = response.json()
        print("\nPUSH_SMS Response:")
        print(json.dumps(response_data, indent=2))
        return response_data
    except Exception as e:
        logger.error(f"Error making request: {e}")
        return None

if __name__ == "__main__":
    # Test GET_SERVICES
    print("\n=== Testing GET_SERVICES ===")
    result = test_get_services()
    
    # Test GET_NUMBER
    print("\n=== Testing GET_NUMBER ===")
    phone_number = test_get_number()
    
    # Test PUSH_SMS with the phone number we got
    print("\n=== Testing PUSH_SMS ===")
    if phone_number:
        sms_result = test_push_sms(phone_number, "Test SMS message")
        
        # Test FINISH_ACTIVATION with the phone number if we got one
        print("\n=== Testing FINISH_ACTIVATION ===")
        if sms_result and sms_result.get('status') == 'SUCCESS':
            test_finish_activation(phone_number, status=3)  # Mark as successfully sold
    else:
        print("No phone number received from GET_NUMBER, skipping PUSH_SMS test")