# SMS Hub Agent

A Python-based SMS management application that integrates with SMS Hub services. This application provides a GUI interface for managing modems and handling SMS operations.

## Features

- Modem management and monitoring
- SMS Hub service integration
- Real-time status updates
- GUI interface for easy operation
- REST API endpoints for service integration

## Setup

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Configure your settings in `config.json`

3. Run the application:
```bash
python main.py
```

## API Endpoints

- `GET_SERVICES`: Retrieve available services and modem status
- `GET_NUMBER`: Request a phone number for activation
- `FINISH_ACTIVATION`: Complete the activation process

## Configuration

Edit `config.json` to customize:
- API credentials
- Service settings
- Modem configurations

## Requirements

- Python 3.x
- Flask
- PyQt5 (for GUI)
- Additional dependencies in requirements.txt
