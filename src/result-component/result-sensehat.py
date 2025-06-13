"""
GreengrassV2 component code
Deploy to Raspberry Pi or compatible edge compute device
Requres recipe.json for full component deployment
Listens on MQTT topic, created using thing attributes: clientId, deviceId
MQTT topic: client/{clientId}/{deviceId}/result

Expected message format:
{
  "analysis": {
    "priority": 2,
    "summary": "The image shows a work area with ...",
    "description": "The bookshelf appears to be ...",
    "oshaReference": "OSHA Standard ...."
  },
  "token_usage": {
    "input_tokens": 1807,
    "output_tokens": 181,
    "total_tokens": 1988
  },
  "requester": {
    "clientId": "client-3985",
    "deviceId": "device-001",
    "timestamp": "2025-03-25T17:51:10+00:00"
  }
}

"""

import sys
import time
import traceback
import json
import logging
import os
import boto3
from datetime import datetime
import awsiot.greengrasscoreipc.clientv2 as clientV2
from botocore.exceptions import ClientError
from sense_hat import SenseHat

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define QoS level for MQTT messages
QOS = 1

# Define LED colors (R,G,B)
LED_COLORS = {
    5: (255, 0, 0),   # Red
    4: (255, 69, 0),    # Red orange
    3: 	(255, 165, 0),  # Orange
    2: (255, 255, 0),   # Yellow
    1: 	(0, 128, 0),    # Green
    'default': (255, 255, 255)  # White
}

class LEDController:
    def __init__(self):
        try:
            self.sense = SenseHat()
            self.sense.clear()  # Clear LED matrix on initialization
            self.sense.low_light = True  # Optional: reduce brightness
            logger.info("Successfully initialized Sense HAT")
            
            # Test LED functionality at startup
            self.test_led_matrix()
        except Exception as e:
            logger.error(f"Failed to initialize Sense HAT: {str(e)}")
            self.sense = None

    def test_led_matrix(self):
        """Test LED matrix at startup with a quick color cycle"""
        try:
            logger.info("Testing LED matrix...")
            for priority, color in LED_COLORS.items():
                if priority != 'default':
                    logger.info(f"Testing priority {priority} with color {color}")
                    self.sense.clear(color)
                    time.sleep(0.5)
            self.sense.clear()
            logger.info("LED matrix test completed")
        except Exception as e:
            logger.error(f"LED matrix test failed: {str(e)}")

    def flash_priority(self, priority):
        """Flash LED matrix based on priority level"""
        if not self.sense:
            logger.error("Sense HAT not initialized - cannot display priority")
            return

        try:
            # Convert priority to int if it's a string
            if isinstance(priority, str):
                try:
                    priority = int(priority)
                    logger.info(f"Converted priority string to integer: {priority}")
                except ValueError:
                    logger.error(f"Invalid priority value: {priority}")
                    priority = None

            # Get color based on priority
            color = LED_COLORS.get(priority, LED_COLORS['default'])
            logger.info(f"Setting LED color for priority {priority}: RGB{color}")
            
            # Flash three times
            for flash_count in range(3):
                logger.debug(f"Flash sequence {flash_count + 1}/3")
                
                # Fill with color
                logger.debug(f"Setting color to RGB{color}")
                self.sense.clear(color)
                time.sleep(1)
                
                # Turn off
                logger.debug("Clearing display")
                self.sense.clear()
                time.sleep(0.5)
                
            logger.info("Flash sequence completed")
            
        except Exception as e:
            logger.error(f"Error controlling LED matrix: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
        finally:
            try:
                self.sense.clear()  # Ensure LEDs are off when done
                logger.debug("LED matrix cleared")
            except Exception as e:
                logger.error(f"Error clearing LED matrix: {str(e)}")


class ResultSubscriber:
    def __init__(self):
        self.ipc_client = None
        self.aws_session = None
        self.topic = None
        self.thing_name = None
        self.company_id = None
        self.device_id = None
        logger.info("Initializing LED Controller")
        self.led_controller = LEDController()

    def get_thing_attributes(self):
        """Get thing name and attributes using Token Exchange Service"""
        try:
            # Initialize IPC client for token exchange
            self.ipc_client = clientV2.GreengrassCoreIPCClientV2()
            
            # Get thing name from environment variable
            self.thing_name = os.environ.get('AWS_IOT_THING_NAME')
            if not self.thing_name:
                logger.error("Thing name not found in environment variables")
                return False
                
            logger.info(f"Retrieved thing name: {self.thing_name}")

            # Check for required Token Exchange Service environment variables
            if (os.environ.get('AWS_CONTAINER_CREDENTIALS_FULL_URI') and 
                os.environ.get('AWS_CONTAINER_AUTHORIZATION_TOKEN')):
                logger.info("Token Exchange Service environment variables are configured")
                self.aws_session = boto3.Session()
                iot_client = self.aws_session.client('iot')
                
                # Describe thing to get attributes
                response = iot_client.describe_thing(thingName=self.thing_name)
                
                if 'attributes' in response:
                    attributes = response['attributes']
                    self.company_id = attributes.get('companyId')
                    self.device_id = attributes.get('deviceId')

                    if self.company_id and self.device_id:
                        self.topic = f"client/{self.company_id}/{self.device_id}/result"
                        logger.info(f"Successfully constructed topic: {self.topic}")
                        return True
                    else:
                        logger.error("Required attributes 'companyId' or 'deviceId' not found")
                        return False
                else:
                    logger.error("No attributes found for thing")
                    return False
                    
            else:
                logger.error("Missing required Token Exchange Service environment variables")
                logger.error("Required: AWS_CONTAINER_CREDENTIALS_FULL_URI and AWS_CONTAINER_AUTHORIZATION_TOKEN")
                return False
        except Exception as e:
            logger.error(f"Error getting thing attributes: {str(e)}")
            raise

    def process_priority(self, message_json):
        """Extract and process priority from message"""
        try:
            logger.info(f"Processing message for priority: {json.dumps(message_json, indent=2)}")
            
            if 'analysis' in message_json:
                if 'priority' in message_json['analysis']:
                    priority = message_json['analysis']['priority']
                    logger.info(f"Found priority in message: {priority}")
                    self.led_controller.flash_priority(priority)
                else:
                    logger.warning("No 'priority' field found in analysis")
                    logger.debug(f"Analysis content: {json.dumps(message_json['analysis'], indent=2)}")
            else:
                logger.warning("No 'analysis' field found in message")
            
        except Exception as e:
            logger.error(f"Error processing priority: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")


    def on_message_received(self, event):
        """Handle incoming MQTT messages"""
        try:
            message = str(event.message.payload, 'utf-8')
            topic = event.message.topic_name
            
            logger.info(f"Received message on topic: {topic}")
            logger.debug(f"Raw message content: {message}")
            
            try:
                # Parse and pretty print the JSON message
                message_json = json.loads(message)
                formatted_message = json.dumps(message_json, indent=2)
                logger.info(f"Parsed JSON message:\n{formatted_message}")
                
                # Process priority and control LEDs
                self.process_priority(message_json)
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON message: {str(e)}")
                logger.warning("Raw message content:")
                logger.warning(message)
                
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")

    def run(self):
        """Main execution method"""
        try:
            logger.info("Starting Result Subscriber Component")
            
            # Get thing attributes using Token Exchange Service
            if not self.get_thing_attributes():
                raise Exception("Failed to get thing attributes")

            # Initialize IPC client
            self.ipc_client = clientV2.GreengrassCoreIPCClientV2()
            
            # Subscribe to topic
            _, operation = self.ipc_client.subscribe_to_iot_core(
                topic_name=self.topic,
                qos=QOS,
                on_stream_event=self.on_message_received,
                on_stream_error=lambda x: logger.error(f"Stream error: {x}"),
                on_stream_closed=lambda: logger.info("Stream closed")
            )
            
            logger.info(f"Successfully subscribed to topic: {self.topic}")
            
            # Keep the main thread alive
            try:
                while True:
                    time.sleep(10)
            except InterruptedError:
                logger.info("Subscribe interrupted.")
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
            finally:
                operation.close()
                self.ipc_client.close()
                
        except Exception as e:
            logger.error(f"Exception occurred: {str(e)}")
            traceback.print_exc()
            sys.exit(1)

def main():
    subscriber = ResultSubscriber()
    subscriber.run()

if __name__ == "__main__":
    main()
