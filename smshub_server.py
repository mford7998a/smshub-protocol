import logging
import time
from typing import Dict, Optional, List
from flask import Flask, request, jsonify
from config import config
from tunnel_manager import TunnelManager
from setup_localtonet import ensure_localtonet_setup
import threading
from datetime import datetime
from flask_cors import CORS
from flask_compress import Compress
import os
import json
#from api_logger import APILogger

# Remove duplicate logging initialization, just get the logger
logger = logging.getLogger(__name__)

class SmsHubServer:
    def __init__(self):
        """Initialize SMS Hub server."""
        self.app = Flask(__name__)
        self.modems = {}
        self.active_numbers = {}
        self.completed_activations = {}
        self.activation_log_file = 'activations.log'
        self.stats = {
            'total_activations': 0,
            'completed_activations': 0,
            'cancelled_activations': 0,
            'refunded_activations': 0,
            'total_earnings': 0.0,
            'service_stats': {},
            'activation_times': []
        }
        
        # Initialize SMS Hub client
        try:
            from smshub_api import SmsHubAPI, SmsHubConfig
            api_config = SmsHubConfig(
                api_key=config.get('smshub_api_key'),
                agent_id=config.get('smshub_agent_id'),
                server_url=config.get('server_url'),
                api_url="https://agent.unerio.com/agent/api/sms"  # From docs
            )
            self.smshub = SmsHubAPI(api_config)
            # Also initialize the integration with the same API key
            from smshub_integration import SmsHubIntegration
            self.smshub_integration = SmsHubIntegration(
                base_url="https://agent.unerio.com/agent/api/sms",  # Exact URL from docs
                api_key="15431U1ea5e5b53572512438b03fbe8f96fa10"  # Hardcoded API key
            )
            logger.info("SMS Hub integration initialized with URL: https://agent.unerio.com/agent/api/sms")
            logger.info("SMS Hub client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize SMS Hub client: {e}")
            self.smshub = None
            self.smshub_integration = None
        
        # Initialize services
        self.services = config.get('services', {})  # Get services from config.json
        
        # Initialize activation logger
        try:
            from activation_logger import ActivationLogger
            self.activation_logger = ActivationLogger()
            logger.info("Activation logger initialized")
        except ImportError:
            logger.warning("ActivationLogger module not found, logging will be limited")
            self.activation_logger = None
        except Exception as e:
            logger.error(f"Error initializing activation logger: {e}")
            self.activation_logger = None
        
        # Service name mapping
        self.service_map = {
            'whatsapp': 'wa',
            'telegram': 'tg',
            'viber': 'vi',
            'facebook': 'fb',
            'instagram': 'ig',
            'twitter': 'tw',
            'uber': 'ub',
            'gmail': 'gm',
            'yahoo': 'ya',
            'microsoft': 'mc',
            'amazon': 'am',
            'netflix': 'nf',
            'spotify': 'sf',
            'tinder': 'tn'
        }
        
        # Initialize routes
        self._init_routes()
        
        self.load_total_earnings()
        
    def _init_routes(self):
        """Initialize Flask routes."""
        self.app.route('/', methods=['POST'])(self.handle_request)
        
    def handle_request(self):
        """Handle incoming requests."""
        try:
            data = request.get_json()
            action = data.get('action')
            
            if not action:
                return jsonify({
                    'status': 'ERROR',
                    'error': 'Missing action'
                })
            
            # Route to appropriate handler
            if action == 'GET_SERVICES':
                return self.handle_get_services(data)
            elif action == 'GET_NUMBER':
                return self.handle_get_number(data)
            elif action == 'FINISH_ACTIVATION':
                return self.handle_finish_activation(data)
            else:
                return jsonify({
                    'status': 'ERROR',
                    'error': f'Unknown action: {action}'
                })
                
        except Exception as e:
            logger.error(f"Error handling request: {e}", exc_info=True)
            return jsonify({
                'status': 'ERROR',
                'error': 'Internal Server Error'
            })
            
    def handle_get_number(self, data):
        """Handle GET_NUMBER request."""
        try:
            logger.info("=" * 80)
            logger.info("INCOMING REQUEST: GET_NUMBER")
            logger.info(f"Request Data: {json.dumps(data, indent=2)}")
            logger.info("-" * 80)

            # Validate required fields
            service = data.get('service')
            if not service:
                error_response = {
                    'status': 'ERROR',
                    'error': 'Missing service'
                }
                logger.error(f"Validation Error: {error_response['error']}")
                logger.info(f"Response: {json.dumps(error_response, indent=2)}")
                logger.info("=" * 80)
                return jsonify(error_response)
                
            # Store original service code exactly as received
            service_code = service  # Don't modify the service code
                
            # Check if service is enabled in config
            if not config.get('services', {}).get(service_code, False):
                logger.error(f"Service not enabled in config: {service_code}")
                error_response = {
                    'status': 'ERROR',
                    'error': f'Service not available: {service_code}'
                }
                logger.info(f"Response: {json.dumps(error_response, indent=2)}")
                logger.info("=" * 80)
                return jsonify(error_response)
                
            # Handle exception phone set
            exception_phones = data.get('exceptionPhoneSet', [])
            logger.info(f"Exception phones: {exception_phones}")
            
            # Find available number
            available_port = None
            available_phone = None
            
            # Iterate through modems using port as key
            for port, modem in self.modems.items():
                if modem['status'] != 'active':
                    continue
                    
                phone = modem.get('phone', '')
                if not phone or phone == 'Unknown':
                    continue
                    
                # Clean phone number for comparison (remove '+' and any spaces)
                clean_phone = phone.lstrip('+').replace(' ', '')
                
                # Check if number is in exception list
                is_excluded = False
                for prefix in exception_phones:
                    if clean_phone.startswith(str(prefix)):
                        is_excluded = True
                        break
                        
                if is_excluded:
                    continue
                    
                available_port = port
                available_phone = phone
                break
                
            if not available_port or not available_phone:
                no_numbers_response = {'status': 'NO_NUMBERS'}
                logger.info("No available numbers found")
                logger.info(f"Response: {json.dumps(no_numbers_response, indent=2)}")
                logger.info("=" * 80)
                return jsonify(no_numbers_response)
                
            # Generate activation ID
            activation_id = int(time.time() * 1000)
            logger.info(f"Generated activation ID: {activation_id}")
            
            # Update modem status
            self.modems[available_port]['status'] = 'busy'
            self.modems[available_port]['activation_id'] = activation_id
            logger.info(f"Updated modem status - Port: {available_port}, Status: busy")
            
            # Store activation with original service code
            self.active_numbers[available_phone] = {
                'activation_id': activation_id,
                'service': service_code,  # Store exact service code from request
                'timestamp': time.time(),
                'sum': data.get('sum', 0),
                'port': available_port  # Store port for reference
            }
            logger.info(f"Stored activation data for phone: {available_phone}")
            
            # Update stats
            self.stats['total_activations'] += 1
            
            # Return phone number without + prefix as required by API
            success_response = {
                'status': 'SUCCESS',
                'number': available_phone.lstrip('+'),
                'activationId': activation_id
            }
            logger.info(f"Response: {json.dumps(success_response, indent=2)}")
            logger.info("=" * 80)
            return jsonify(success_response)
            
        except Exception as e:
            logger.error(f"Error in get_number: {e}", exc_info=True)
            error_response = {
                'status': 'ERROR',
                'error': 'Internal Server Error'
            }
            logger.info(f"Response: {json.dumps(error_response, indent=2)}")
            logger.info("=" * 80)
            return jsonify(error_response)

    def handle_finish_activation(self, data):
        """Handle FINISH_ACTIVATION request."""
        try:
            logger.info("=" * 80)
            logger.info("INCOMING REQUEST: FINISH_ACTIVATION")
            logger.info(f"Request Data: {json.dumps(data, indent=2)}")
            logger.info("-" * 80)

            activation_id = data.get('activationId')
            status = data.get('status')
            
            if not activation_id or status is None:
                error_response = {
                    'status': 'ERROR',
                    'error': 'Missing required fields'
                }
                logger.error("Missing required fields in finish activation request")
                logger.info(f"Response: {json.dumps(error_response, indent=2)}")
                logger.info("=" * 80)
                return jsonify(error_response)
                
            # Find the phone number for this activation
            found_phone = None
            found_port = None
            
            for phone, activation in self.active_numbers.items():
                if activation.get('activation_id') == activation_id:
                    found_phone = phone
                    found_port = activation.get('port')
                    break
                    
            if not found_phone:
                logger.warning(f"No active number found for activation ID: {activation_id}")
                success_response = {'status': 'SUCCESS'}  # Still return success per protocol
                logger.info(f"Response: {json.dumps(success_response, indent=2)}")
                logger.info("=" * 80)
                return jsonify(success_response)
                
            # Handle the activation status
            if status == 8:  # Activation complete
                logger.info(f"Activation {activation_id} completed successfully")
                if found_port and found_port in self.modems:
                    self.modems[found_port]['status'] = 'active'
                    logger.info(f"Reset modem status to active for port: {found_port}")
                if found_phone in self.active_numbers:
                    del self.active_numbers[found_phone]
                    logger.info(f"Removed activation for phone: {found_phone}")
                    
            elif status == 3:  # SMS received successfully
                logger.info(f"SMS received successfully for activation {activation_id}")
                
            elif status == 1:  # Waiting for SMS
                logger.info(f"Waiting for SMS for activation {activation_id}")
                
            elif status == 2:  # SMS code not valid
                logger.warning(f"SMS code not valid for activation {activation_id}")
                
            elif status == 4:  # Timeout
                logger.warning(f"Timeout for activation {activation_id}")
                if found_port and found_port in self.modems:
                    self.modems[found_port]['status'] = 'active'
                    logger.info(f"Reset modem status to active for port: {found_port}")
                if found_phone in self.active_numbers:
                    del self.active_numbers[found_phone]
                    logger.info(f"Removed activation for phone: {found_phone}")
                    
            else:
                logger.warning(f"Received unknown status code: {status} for activation {activation_id}")
            
            success_response = {'status': 'SUCCESS'}
            logger.info(f"Response: {json.dumps(success_response, indent=2)}")
            logger.info("=" * 80)
            return jsonify(success_response)

        except Exception as e:
            logger.error(f"Error in finish_activation: {e}", exc_info=True)
            error_response = {
                'status': 'ERROR',
                'error': 'Internal Server Error'
            }
            logger.info(f"Response: {json.dumps(error_response, indent=2)}")
            logger.info("=" * 80)
            return jsonify(error_response)

    def save_activation(self, phone: str, service: str, status: str):
        """Save activation to history file."""
        try:
            if status == 'completed':  # Only save completed activations
                timestamp = time.time()
                # Get activation details from active_numbers
                activation_details = self.active_numbers.get(phone, {})
                activation_id = activation_details.get('activation_id', 'unknown')
                
                entry = {
                    'activation_id': activation_id,
                    'phone': phone,
                    'service': service,
                    'timestamp': timestamp,
                    'date': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp)),
                    'status': status,
                    'sum': activation_details.get('sum', 0)
                }
                
                # Update in-memory record
                if phone not in self.completed_activations:
                    self.completed_activations[phone] = {}
                self.completed_activations[phone][service] = {
                    'timestamp': timestamp,
                    'activation_id': activation_id
                }
                
                # Append to file
                with open(self.activation_log_file, 'a') as f:
                    f.write(json.dumps(entry) + '\n')
                    
                logger.info(f"Saved activation: {phone} - {service} - Activation ID: {activation_id}")
        except Exception as e:
            logger.error(f"Error saving activation: {e}")

    def handle_push_sms(self, data):
        """Handle PUSH_SMS request."""
        try:
            logger.info("=" * 80)
            logger.info("INCOMING REQUEST: PUSH_SMS")
            logger.info(f"Request Data: {json.dumps(data, indent=2)}")
            logger.info("-" * 80)

            sms_id = data.get('smsId')
            phone = data.get('phone')
            phone_from = data.get('phoneFrom')
            text = data.get('text')

            if not all([sms_id, phone, phone_from, text]):
                error_response = {
                    'status': 'ERROR',
                    'error': 'Missing required fields'
                }
                logger.error("Missing required fields in push SMS request")
                logger.info(f"Response: {json.dumps(error_response, indent=2)}")
                logger.info("=" * 80)
                return jsonify(error_response)

            # Validate types
            if not isinstance(sms_id, (int, float)) or not isinstance(phone, (int, float)):
                error_response = {
                    'status': 'ERROR',
                    'error': 'Invalid field types'
                }
                logger.error("Invalid field types in push SMS request")
                logger.info(f"Response: {json.dumps(error_response, indent=2)}")
                logger.info("=" * 80)
                return jsonify(error_response)

            # Find active activation for this phone number
            str_phone = str(phone)
            activation = self.active_numbers.get(str_phone)
            if not activation:
                logger.warning(f"Received SMS for unknown activation: {phone}")
                error_response = {
                    'status': 'ERROR',
                    'error': 'No active activation found for this number'
                }
                logger.info(f"Response: {json.dumps(error_response, indent=2)}")
                logger.info("=" * 80)
                return jsonify(error_response)

            # Forward SMS to SMSHUB immediately
            try:
                if self.smshub:  # Make sure smshub client is initialized
                    logger.info("Forwarding SMS to SMSHUB")
                    response = self.smshub.push_sms(
                        sms_id=sms_id,
                        phone=phone,  # Already validated as int
                        phone_from=phone_from,
                        text=text
                    )
                    if response:
                        logger.info(f"Successfully forwarded SMS to SMSHUB - ID: {sms_id}")
                        success_response = {'status': 'SUCCESS'}
                        logger.info(f"Response: {json.dumps(success_response, indent=2)}")
                        logger.info("=" * 80)
                        return jsonify(success_response)
                    else:
                        logger.error(f"Failed to forward SMS to SMSHUB - ID: {sms_id}")
                        error_response = {
                            'status': 'ERROR',
                            'error': 'Failed to forward SMS'
                        }
                        logger.info(f"Response: {json.dumps(error_response, indent=2)}")
                        logger.info("=" * 80)
                        return jsonify(error_response)
                else:
                    logger.error("SMSHUB client not initialized")
                    error_response = {
                        'status': 'ERROR',
                        'error': 'SMSHUB client not initialized'
                    }
                    logger.info(f"Response: {json.dumps(error_response, indent=2)}")
                    logger.info("=" * 80)
                    return jsonify(error_response)
            except Exception as e:
                logger.error(f"Error forwarding SMS to SMSHUB: {e}", exc_info=True)
                error_response = {
                    'status': 'ERROR',
                    'error': 'Internal Server Error'
                }
                logger.info(f"Response: {json.dumps(error_response, indent=2)}")
                logger.info("=" * 80)
                return jsonify(error_response)
        except Exception as e:
            logger.error(f"Error in push_sms: {e}", exc_info=True)
            error_response = {
                'status': 'ERROR',
                'error': 'Internal Server Error'
            }
            logger.info(f"Response: {json.dumps(error_response, indent=2)}")
            logger.info("=" * 80)
            return jsonify(error_response)

    def register_modem(self, key: str, modem_info: dict):
        """Register a modem with the server."""
        try:
            logger.info(f"Registering modem with key: {key}")
            logger.info(f"Modem info: {modem_info}")
            
            # Set required fields
            modem_info['operator'] = 'physic'
            modem_info['country'] = 'usaphysical'
            
            # Use port as key instead of phone number
            port = modem_info.get('port')
            if not port:
                logger.error("No port specified in modem_info")
                raise ValueError("No port specified in modem_info")
            
            # Store modem info using port as key
            self.modems[port] = modem_info
            logger.info(f"Successfully registered modem: {port} with status: {modem_info.get('status', 'unknown')}")
            logger.info(f"Current modems: {self.modems}")
            
        except Exception as e:
            logger.error(f"Error registering modem: {e}")
            logger.error("Full error details:", exc_info=True)
            raise

    def unregister_modem(self, phone_number: str) -> None:
        """Unregister a modem."""
        if phone_number in self.modems:
            logger.info(f"Unregistering modem: {phone_number}")
            self.modems.pop(phone_number)

    def get_service_quantities(self):
        """Get current quantities for all services."""
        try:
            # Count active modems
            active_modems = len([m for m in self.modems.values() 
                               if m.get('status') == 'active'])
            
            # Return quantities for enabled services
            return {
                service: {
                    'quantity': active_modems,
                    'active': len([1 for num in self.active_numbers.values() 
                                 if num.get('service') == service]),
                    'completed': len([1 for nums in self.completed_activations.values() 
                                    if service in nums])
                }
                for service, enabled in config.get('services', {}).items()
                if enabled
            }
        except Exception as e:
            logger.error(f"Error getting service quantities: {e}")
            return {}

    def run(self):
        """Run the server."""
        self.app.run(
            host=self.host, 
            port=self.port, 
            debug=False, 
            threaded=True
        )

    def stop(self):
        """Stop the server and cleanup."""
        pass

    def handle_incoming_sms(self, phone: str, sender: str, text: str):
        """Handle incoming SMS message."""
        try:
            # Log the incoming SMS first
            logger.info("========== HANDLING INCOMING SMS ==========")
            logger.info(f"Original Phone: {phone}")
            logger.info(f"Sender: {sender}")
            logger.info(f"Text: {text}")
            
            # First, strip any '+' symbols and spaces - they're just formatting
            clean_phone = phone.lstrip('+').replace(' ', '').replace('-', '')
            
            # Now apply US phone number rules:
            # - If 10 digits, add '1' prefix
            # - If 11 digits, must start with '1'
            # - Any other length is invalid
            if len(clean_phone) == 10:
                normalized_phone = '1' + clean_phone
            elif len(clean_phone) == 11 and clean_phone.startswith('1'):
                normalized_phone = clean_phone
            else:
                logger.error(f"Invalid phone number format: {phone} (cleaned: {clean_phone})")
                return False
                
            logger.info(f"Normalized phone: {normalized_phone}")
            
            # Look up activation with normalized number
            activation = self.active_numbers.get(normalized_phone)
            if not activation:
                logger.warning(f"Received SMS for unknown activation: {normalized_phone}")
                logger.warning(f"Available active numbers: {list(self.active_numbers.keys())}")
                return False
            
            # Generate SMS ID
            sms_id = int(time.time() * 1000)  # Use timestamp as SMS ID
            logger.info(f"Generated SMS ID: {sms_id}")
            
            # Forward to SMS Hub with retries
            max_retries = 3
            retry_delay = 1
            
            for attempt in range(max_retries):
                try:
                    if not self.smshub:
                        logger.error("SMS Hub client not initialized")
                        return False
                        
                    # Clean phone number and sender for API request
                    clean_phone = normalized_phone.lstrip('+').replace('-', '').replace(' ', '')
                    clean_sender = sender.lstrip('+').replace('-', '').replace(' ', '')
                    
                    # Get the exact service code that was stored from GET_NUMBER
                    service_code = activation.get('service')  # Use directly, no mapping needed
                    logger.info(f"Using original service code from GET_NUMBER request: '{service_code}'")
                    
                    # Log the request details
                    logger.info(f"Sending SMS to SMS Hub - Attempt {attempt + 1}")
                    request_data = {
                        "smsId": sms_id,
                        "phoneFrom": service_code,  # Use exact service code from activation
                        "phone": int(clean_phone),
                        "text": text,
                        "action": "PUSH_SMS",
                        "key": "15431U1ea5e5b53572512438b03fbe8f96fa10"
                    }
                    logger.info(f"Request details: {json.dumps(request_data, indent=2)}")
                    
                    # Make the API call using smshub instead of smshub_integration
                    response = self.smshub.push_sms(
                        sms_id=sms_id,
                        phone=int(clean_phone),  # Must be numeric
                        phone_from=service_code,  # Pass service code instead of sender
                        text=text
                    )
                    
                    # Log the raw response for debugging
                    logger.info(f"SMS Hub raw response: {response}")
                    
                    # Handle both boolean and dictionary response formats
                    if isinstance(response, bool):
                        success = response
                    elif isinstance(response, dict):
                        success = response.get('status') == 'SUCCESS'
                    else:
                        success = False
                        
                    if success:
                        logger.info(f"Successfully forwarded SMS to SMS Hub - ID: {sms_id}")
                        # Log successful delivery
                        self.log_sms_delivery(
                            activation_id=activation['activation_id'],
                            sms_text=text,
                            delivery_status='delivered'
                        )
                        return True
                    else:
                        logger.warning(f"Failed to forward SMS - Attempt {attempt + 1}/{max_retries}")
                        if attempt < max_retries - 1:  # Don't sleep on last attempt
                            time.sleep(retry_delay)
                    
                except Exception as e:
                    logger.error(f"Error forwarding SMS (attempt {attempt + 1}): {str(e)}")
                    logger.error("Full error details:", exc_info=True)
                    if attempt < max_retries - 1:  # Don't sleep on last attempt
                        time.sleep(retry_delay)
            
            logger.error("Failed to forward SMS after 3 attempts")
            return False
            
        except Exception as e:
            logger.error(f"Error in handle_incoming_sms: {e}")
            logger.error("Full error details:", exc_info=True)
            return False

    def handle_get_services(self, data):
        """Handle GET_SERVICES request."""
        try:
            # Validate API key
            key = data.get('key')
            if not key:
                return jsonify({
                    'status': 'ERROR',
                    'error': 'Missing API key'
                })

            # Count active modems
            active_modems = len([m for m in self.modems.values() 
                               if m.get('status') == 'active'])

            logger.info(f"GET_SERVICES request - Active modems: {active_modems}")
            logger.debug(f"Current modems: {self.modems}")

            # Get enabled services from config
            enabled_services = config.get('services', {})

            # Create operator map with services
            operator_map = {}
            for service_id, enabled in enabled_services.items():
                if enabled:  # Only include enabled services
                    operator_map[service_id] = active_modems

            # Always return a response with the country list
            country_list = [{
                'country': 'usaphysical',
                'operatorMap': {
                    'physic': operator_map
                }
            }]

            response = {
                'status': 'SUCCESS',
                'countryList': country_list
            }

            logger.info(f"GET_SERVICES response: {response}")
            return jsonify(response)

        except Exception as e:
            logger.error(f"Error in get_services: {e}", exc_info=True)
            return jsonify({
                'status': 'ERROR',
                'error': 'Internal Server Error'
            })

    def log_activation_status(self, activation_id: int, status: int, phone: str = None):
        """Log activation status change."""
        try:
            if self.activation_logger:
                self.activation_logger.log_activation_status_update(
                    activation_id=activation_id,
                    status=status,
                    additional_data={'phone': phone}
                )
            else:
                # Fallback to basic logging
                logger.info(f"Activation status change - ID: {activation_id}, Status: {status}, Phone: {phone}")
        except Exception as e:
            logger.error(f"Error logging activation status: {e}")

    def log_sms_delivery(self, activation_id: int, sms_text: str, delivery_status: str):
        """Log SMS delivery status."""
        try:
            if self.activation_logger:
                self.activation_logger.log_sms_delivered(
                    activation_id=activation_id,
                    text=sms_text,
                    recipient='SMS Hub',
                    delivery_status=delivery_status
                )
            else:
                # Fallback to basic logging
                logger.info(f"SMS delivery - ID: {activation_id}, Status: {delivery_status}, Text: {sms_text}")
        except Exception as e:
            logger.error(f"Error logging SMS delivery: {e}")
            logger.error("Full error details:", exc_info=True)

    def load_total_earnings(self):
        """Initialize total earnings from database"""
        self.stats['total_earnings'] = self.activation_logger.get_earnings_by_timeframe()