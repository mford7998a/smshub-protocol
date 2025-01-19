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
from activation_history import ActivationHistoryManager

logger = logging.getLogger(__name__)

class SmsHubServer:
    def load_total_earnings(self):
        """Initialize total earnings from database"""
        try:
            if self.activation_logger:
                self.stats['total_earnings'] = self.activation_logger.get_earnings_by_timeframe()
            else:
                self.stats['total_earnings'] = 0.0
                logger.warning("No activation logger - initializing earnings to 0")
        except Exception as e:
            self.stats['total_earnings'] = 0.0
            logger.error(f"Error loading total earnings: {e}")

    def __init__(self):
        """Initialize SMS Hub server."""
        print("SmsHubServer initialized")
        self.app = Flask(__name__)
        self.modems = {}
        self.active_numbers = {}
        self.completed_activations = {}
        self.activation_log_file = 'activations.log'
        self.host = '0.0.0.0'
        self.port = 5000
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
                api_url="https://agent.unerio.com/agent/api/sms"
            )
            self.smshub = SmsHubAPI(api_config)
            # Also initialize the integration with the same API key
            from smshub_integration import SmsHubIntegration
            self.smshub_integration = SmsHubIntegration(
                base_url="https://agent.unerio.com/agent/api/sms",
                api_key="15431U1ea5e5b53572512438b03fbe8f96fa10"
            )
            logger.info("SMS Hub integration initialized with URL: https://agent.unerio.com/agent/api/sms")
            logger.info("SMS Hub client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize SMS Hub client: {e}")
            self.smshub = None
            self.smshub_integration = None

        # Initialize services
        self.services = config.get('services', {})

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

    def handle_get_services(self, data):
        """Handle request for available services."""
        try:
            services = self.get_service_quantities()
            return jsonify({
                'status': 'SUCCESS',
                'services': services
            })
        except Exception as e:
            logger.error(f"Error handling get services request: {e}", exc_info=True)
            return jsonify({
                'status': 'ERROR',
                'error': 'Failed to retrieve services'
            })

    def run(self):
        """Run the server."""
        try:
            logger.info("Starting SMS Hub server...")
            logger.info(f"Host: {self.host}")
            logger.info(f"Port: {self.port}")
            
            # Verify modems are initialized
            if not self.modems:
                logger.warning("No modems initialized - server may not function properly")
                
            # Verify services are configured
            if not config.get('services'):
                logger.warning("No services configured in config.json - using default services")
                
            try:
                self.app.run(
                    host=self.host,
                    port=self.port,
                    debug=False,
                    threaded=True
                )
            except Exception as e:
                logger.error(f"Failed to start server: {str(e)}")
                logger.error("Full error details:", exc_info=True)
                raise
        except Exception as e:
            logger.error(f"Failed to initialize server: {str(e)}")
            logger.error("Full error details:", exc_info=True)
            raise

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
