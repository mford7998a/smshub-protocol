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

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SmsHubServer:
    def __init__(self, host='0.0.0.0', port=None):
        self.host = host
        self.port = port or config.get('server_port', 5000)
        self.app = Flask(__name__)
        self.app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
        self.app.config['JSON_AS_ASCII'] = False
        #self.api_logger = APILogger()
        
        # Enable CORS and compression
        CORS(self.app)
        compress = Compress()
        compress.init_app(self.app)
        
        # Configure response headers
        
        
        # Initialize components
        self.modems = {}  # port/phone -> modem_info
        self.active_numbers = {}  # phone -> activation_info
        self.completed_activations = {}  # phone -> {service: completion_time}
        self.smshub = None  # Set by main.py
        
        # Setup routes
        self.setup_routes()

    def setup_routes(self):
        """Setup Flask routes."""
        @self.app.route('/', methods=['GET', 'POST'])
        @self.app.route('/smshub', methods=['GET', 'POST'])
        def handle_smshub_request():
            """Handle all SMS Hub requests."""
            try:
                # For GET requests, show status page
                if request.method == 'GET':
                    return jsonify({
                        'status': 'running',
                        'modems': len(self.modems),
                        'active_numbers': len(self.active_numbers)
                    })
                
                # Log request details for debugging
                logger.debug("Request details:")
                logger.debug(f"Method: {request.method}")
                logger.debug(f"Headers: {dict(request.headers)}")
                logger.debug(f"Data: {request.get_data(as_text=True)}")
                
                # Parse JSON data
                try:
                    data = request.get_json()
                    if not data:
                        logger.error("No data provided in request")
                        return jsonify({
                            'status': 'ERROR',
                            'error': 'No data provided'
                        })
                except Exception as e:
                    logger.error(f"Failed to parse JSON data: {e}")
                    return jsonify({
                        'status': 'ERROR',
                        'error': 'Invalid JSON data'
                    })

                # Validate API key
                key = data.get('key')
                action = data.get('action')

                if not key or key != config.get('smshub_api_key'):
                    logger.error(f"Invalid API key: {key}")
                    return jsonify({
                        'status': 'ERROR',
                        'error': 'Invalid API key'
                    })

                # Handle actions
                try:
                    if action == 'GET_SERVICES':
                        logger.info("Handling GET_SERVICES request")
                        response = self.handle_get_services()
                        return response
                    elif action == 'GET_NUMBER':
                        return self.handle_get_number(data)
                    elif action == 'FINISH_ACTIVATION':
                        return self.handle_finish_activation(data)
                    elif action == 'PUSH_SMS':
                        return self.handle_push_sms(data)
                    else:
                        logger.error(f"Unknown action: {action}")
                        return jsonify({
                            'status': 'ERROR',
                            'error': 'Unknown action'
                        })
                except Exception as e:
                    logger.error(f"Error handling {action} request: {e}", exc_info=True)
                    return jsonify({
                        'status': 'ERROR',
                        'error': str(e)
                    })
            except Exception as e:
                logger.error(f"Error handling request: {e}", exc_info=True)
                return jsonify({
                    'status': 'ERROR',
                    'error': 'Internal Server Error'
                })

    def handle_get_services(self):
        """Handle GET_SERVICES request."""
        try:
            # Count active modems
            active_modems = len([m for m in self.modems.values() 
                               if m.get('status') == 'active'])
            
            # Build service quantities map
            service_quantities = {
                service_id: active_modems 
                for service_id, enabled in config.get('services', {}).items()
                if enabled
            }
            
            # Build response in required format
            response = {
                'countryList': [{
                    'country': 'usaphysical',
                    'operatorMap': {
                        'physic': service_quantities
                    }
                }],
                'status': 'SUCCESS'
            }
            
            logger.info(f"GET_SERVICES response: {json.dumps(response, indent=2)}")
            return jsonify(response)
            
        except Exception as e:
            logger.error(f"Error handling GET_SERVICES request: {e}", exc_info=True)
            return jsonify({
                'status': 'ERROR',
                'error': 'Internal Server Error'
            })

    def handle_get_number(self, data):
        """Handle GET_NUMBER request."""
        try:
            country = data.get('country')
            operator = data.get('operator')
            service = data.get('service')
            sum_amount = data.get('sum')
            currency = data.get('currency')
            exception_phones = data.get('exceptionPhoneSet', [])

            if not all([country, operator, service, sum_amount, currency]):
                return jsonify({
                    'status': 'ERROR',
                    'error': 'Missing required fields'
                })

            # Check if service has available numbers
            service_quantity = 0
            for modem in self.modems.values():
                if modem.get('status') == 'active':
                    service_quantity += 1

            if service_quantity == 0:
                logger.info("No numbers available: No active modems found")
                return jsonify({
                    'status': 'NO_NUMBERS'
                })

            # Find available modem
            for phone, modem in self.modems.items():
                if modem.get('status') != 'active':
                    continue

                # Check if phone is in exception list
                if any(phone.startswith(prefix) for prefix in exception_phones):
                    continue

                # Found a match (we don't check operator since all are 'physic')
                modem['status'] = 'busy'
                activation_id = int(time.time())  # Generate unique ID
                modem['activation_id'] = activation_id

                # Record activation
                phone_str = str(phone)  # Convert to string for consistent key type
                self.active_numbers[phone_str] = {
                    'service': service,
                    'timestamp': time.time(),
                    'status': 'active',
                    'sum': sum_amount,
                    'activation_id': activation_id
                }
                logger.info(f"Activation started: ID={activation_id}, Phone={phone_str}, Service={service}, Sum={sum_amount}")
                
                # Update statistics
                self.stats['total_activations'] += 1

                return jsonify({
                    'status': 'SUCCESS',
                    'number': int(phone),  # Must be numeric
                    'activationId': activation_id
                })

            # No suitable numbers found
            logger.info("No numbers available: No suitable modems found")
            return jsonify({
                'status': 'NO_NUMBERS'
            })

        except Exception as e:
            logger.error(f"Error in get_number: {e}", exc_info=True)
            return jsonify({
                'status': 'ERROR',
                'error': 'Internal Server Error'
            })

    def handle_finish_activation(self, data):
        """Handle FINISH_ACTIVATION request."""
        try:
            # Validate required fields
            activation_id = data.get('activationId')
            status = data.get('status')

            if not isinstance(activation_id, (int, float)) or not isinstance(status, (int, float)):
                return jsonify({
                    'status': 'ERROR',
                    'error': 'Invalid field types'
                })

            # Find the activation by ID
            phone = None
            for p, modem in self.modems.items():
                if modem.get('activation_id') == activation_id:
                    phone = p
                    break

            if not phone:
                return jsonify({
                    'status': 'ERROR',
                    'error': 'Activation not found'
                })

            activation = self.active_numbers.get(str(phone))
            if not activation:
                return jsonify({
                    'status': 'ERROR',
                    'error': 'No active activation found'
                })

            # Update activation status based on status code
            if status == 1:  # Waiting for SMS
                logger.info(f"Activation {activation_id} waiting for SMS")
                # No action needed, just keep waiting
            elif status == 3:  # Successfully completed
                self.save_activation(str(phone), activation['service'], 'completed')
                self.stats['completed_activations'] += 1
                self.stats['total_earnings'] += float(activation.get('sum', 0))
                logger.info(f"Activation completed: {phone} - {activation['service']}")
                
                # Update service stats
                service = activation['service']
                if service not in self.stats['service_stats']:
                    self.stats['service_stats'][service] = {'completed': 0, 'cancelled': 0, 'refunded': 0}
                self.stats['service_stats'][service]['completed'] += 1
                
                # Calculate and store activation time
                activation_time = time.time() - activation['timestamp']
                self.stats['activation_times'].append(activation_time)
                
                # Clean up
                self.active_numbers.pop(str(phone), None)
                if str(phone) in self.modems:
                    self.modems[str(phone)]['status'] = 'active'
                    self.modems[str(phone)].pop('activation_id', None)
                
            elif status == 8:  # Cancelled by user
                logger.info(f"Activation cancelled: {phone} - {activation['service']}")
                self.stats['cancelled_activations'] += 1
                
                # Update service stats
                service = activation['service']
                if service not in self.stats['service_stats']:
                    self.stats['service_stats'][service] = {'completed': 0, 'cancelled': 0, 'refunded': 0}
                self.stats['service_stats'][service]['cancelled'] += 1
                
                # Clean up
                self.active_numbers.pop(str(phone), None)
                if str(phone) in self.modems:
                    self.modems[str(phone)]['status'] = 'active'
                    self.modems[str(phone)].pop('activation_id', None)
                
            elif status == 10:  # Refunded
                logger.info(f"Activation refunded: {phone} - {activation['service']}")
                self.stats['refunded_activations'] += 1
                
                # Update service stats
                service = activation['service']
                if service not in self.stats['service_stats']:
                    self.stats['service_stats'][service] = {'completed': 0, 'cancelled': 0, 'refunded': 0}
                self.stats['service_stats'][service]['refunded'] += 1
                
                # Clean up
                self.active_numbers.pop(str(phone), None)
                if str(phone) in self.modems:
                    self.modems[str(phone)]['status'] = 'active'
                    self.modems[str(phone)].pop('activation_id', None)
            
            else:
                logger.warning(f"Received unknown status code: {status} for activation {activation_id}")
            
            return jsonify({
                'status': 'SUCCESS'
            })

        except Exception as e:
            logger.error(f"Error in finish_activation: {e}", exc_info=True)
            return jsonify({
                'status': 'ERROR',
                'error': 'Internal Server Error'
            })

    def save_activation(self, phone: str, service: str, status: str):
        """Save activation to history file."""
        try:
            if status == 'completed':  # Only save completed activations
                timestamp = time.time()
                entry = {
                    'phone': phone,
                    'service': service,
                    'timestamp': timestamp,
                    'date': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
                }
                
                # Update in-memory record
                if phone not in self.completed_activations:
                    self.completed_activations[phone] = {}
                self.completed_activations[phone][service] = timestamp
                
                # Append to file
                with open(self.activation_log_file, 'a') as f:
                    f.write(json.dumps(entry) + '\n')
                    
                logger.info(f"Saved activation: {phone} - {service}")
        except Exception as e:
            logger.error(f"Error saving activation: {e}")

    def handle_push_sms(self, data):
        """Handle PUSH_SMS request."""
        try:
            sms_id = data.get('smsId')
            phone = data.get('phone')
            phone_from = data.get('phoneFrom')
            text = data.get('text')

            if not all([sms_id, phone, phone_from, text]):
                return jsonify({
                    'status': 'ERROR',
                    'error': 'Missing required fields'
                })

            # Validate types
            if not isinstance(sms_id, (int, float)):
                return jsonify({
                    'status': 'ERROR',
                    'error': 'smsId must be numeric'
                })
            if not isinstance(phone, (int, float)):
                return jsonify({
                    'status': 'ERROR',
                    'error': 'phone must be numeric'
                })
            if not isinstance(phone_from, str):
                return jsonify({
                    'status': 'ERROR',
                    'error': 'phoneFrom must be string'
                })
            if not isinstance(text, str):
                return jsonify({
                    'status': 'ERROR',
                    'error': 'text must be string'
                })

            # Log the SMS
            logger.info(f"Received SMS - ID: {sms_id}, From: {phone_from}, To: {phone}, Text: {text}")

            # Find active activation for this phone number
            str_phone = str(phone)
            activation = self.active_numbers.get(str_phone)
            if not activation:
                logger.warning(f"Received SMS for unknown activation: {phone}")
                return jsonify({
                    'status': 'ERROR',
                    'error': 'No active activation found for this number'
                })

            # Forward SMS to SMSHUB immediately
            try:
                if self.smshub:  # Make sure smshub client is initialized
                    response = self.smshub.forward_sms(
                        activation_id=activation.get('activation_id'),
                        sms_text=text,
                        phone_from=phone_from
                    )
                    if response and response.get('status') == 'SUCCESS':
                        logger.info(f"Successfully forwarded SMS to SMSHUB - ID: {sms_id}")
                        return jsonify({
                            'status': 'SUCCESS'
                        })
                    else:
                        logger.error(f"Failed to forward SMS to SMSHUB - ID: {sms_id}, Response: {response}")
                        return jsonify({
                            'status': 'ERROR',
                            'error': 'Failed to forward SMS'
                        })
                else:
                    logger.error("SMSHUB client not initialized")
                    return jsonify({
                        'status': 'ERROR',
                        'error': 'SMSHUB client not initialized'
                    })
            except Exception as e:
                logger.error(f"Error forwarding SMS to SMSHUB: {e}", exc_info=True)
                return jsonify({
                    'status': 'ERROR',
                    'error': 'Internal Server Error'
                })
        except Exception as e:
            logger.error(f"Error in push_sms: {e}", exc_info=True)
            return jsonify({
                'status': 'ERROR',
                'error': 'Internal Server Error'
            })

    def register_modem(self, key: str, modem_info: dict):
        """Register a modem with the server."""
        try:
            logger.info(f"Registering modem with key: {key}")
            modem_info['operator'] = 'physic'
            modem_info['country'] = 'usaphysical'
            self.modems[key] = modem_info
            logger.info(f"Successfully registered modem: {key} with status: {modem_info.get('status', 'unknown')}")
        except Exception as e:
            logger.error(f"Error registering modem: {e}")
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