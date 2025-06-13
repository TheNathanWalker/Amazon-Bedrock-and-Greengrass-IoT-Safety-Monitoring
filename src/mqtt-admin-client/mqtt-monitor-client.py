"""
AWS IoT thing MQTT client code. 
Uses directives in the config.json file to connect to AWS IoT Core and subscribe to a topic, "client/{companyId}/+/result"
Outputs errors and MQTT topic messages to the console.
Does not use ~/.aws/credentials or environment variables.
CompanyId is derived from the thing name, which is derived from the certificate filename.
Listens on MQTT topic, created using thing attribute "companyId"

Requires config.json file with the following structure:
{
    "aws_iot": {
        "endpoint": "a2b6yj7d4cj1gp-ats.iot.us-east-1.amazonaws.com",
        "cert_filepath": "./9971-mqtt-client-certificate.pem.crt",
        "pri_key_filepath": "./9971-mqtt-client-private.pem.key",
        "ca_filepath": "./AmazonRootCA1.pem",
        "region": "us-east-1",
        "qos": 1
    }
}

Permissions are set in the IoT thing principal policy.
See GreengrassV2IoTThingPolicy-MQTT-MONITOR for a minimal-permission example policy.

"""

import os
import json
import ssl
import boto3
from botocore.config import Config as BotoConfig
import paho.mqtt.client as mqtt

class AwsIotMqttClient:
    def __init__(self, config_path='config.json'):
        # Load config.json
        with open(config_path) as f:
            self.config = json.load(f)['aws_iot']

        # Set thing_name first
        self.thing_name = os.path.basename(self.config['cert_filepath']).split('-')[0] + '-mqtt-client'

        # Initialize Boto3 IoT client (no ~/.aws/credentials)
        boto3_session = boto3.Session(region_name=self.config['region'])
        self.iot_client = boto3_session.client('iot', 
                                             config=BotoConfig(region_name=self.config['region']))

        # Get companyId from thing attributes
        self.company_id = self.get_company_id(self.thing_name)

        # Define MQTT topics
        self.mqtt_topic = f"client/{self.company_id}/+/result"
        self.mqtt_topic_wildcard = f"client/{self.company_id}/#"

        # Initialize MQTT client
        self.mqtt_client = mqtt.Client(
            client_id=self.thing_name,
            protocol=mqtt.MQTTv311,
            clean_session=True
        )

        # Set up TLS
        self.mqtt_client.tls_set(
            ca_certs=self.config['ca_filepath'],
            certfile=self.config['cert_filepath'],
            keyfile=self.config['pri_key_filepath'],
            tls_version=ssl.PROTOCOL_TLSv1_2,
        )

        # Enable debugging
        self.mqtt_client.enable_logger()

        # Register callbacks
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.on_disconnect = self.on_disconnect
        self.mqtt_client.on_subscribe = self.on_subscribe
        self.mqtt_client.on_log = self.on_log

        # Add port and keepalive from config or use defaults
        self.config['port'] = self.config.get('port', 8883)
        self.config['keepalive'] = self.config.get('keepalive', 60)

    def get_company_id(self, thing_name):
        try:
            resp = self.iot_client.describe_thing(thingName=thing_name)
            if 'attributes' in resp and 'companyId' in resp['attributes']:
                return resp['attributes']['companyId']
            else:
                raise ValueError(f"Thing {thing_name} does not have a companyId attribute")
        except Exception as e:
            print(f"Error getting company ID for thing {thing_name}: {str(e)}")
            raise

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("Connected to AWS IoT Core!")
            print(f"Thing Name: {self.thing_name}")
            print(f"Company ID: {self.company_id}")
            
            # Subscribe to topics
            self.subscribe_to_topics()
        else:
            print(f"Connection failed with code: {rc}")

    def subscribe_to_topics(self):
        try:
            # Subscribe to specific result topic
            print(f"Attempting to subscribe to: {self.mqtt_topic}")
            result = self.mqtt_client.subscribe(self.mqtt_topic, qos=self.config.get('qos', 1))
            if result[0] == mqtt.MQTT_ERR_SUCCESS:
                print(f"Successfully subscribed to {self.mqtt_topic}")
            else:
                print(f"Failed to subscribe to {self.mqtt_topic}")

            # Subscribe to wildcard topic
            print(f"Attempting to subscribe to: {self.mqtt_topic_wildcard}")
            result = self.mqtt_client.subscribe(self.mqtt_topic_wildcard, qos=self.config.get('qos', 1))
            if result[0] == mqtt.MQTT_ERR_SUCCESS:
                print(f"Successfully subscribed to {self.mqtt_topic_wildcard}")
            else:
                print(f"Failed to subscribe to {self.mqtt_topic_wildcard}")

        except Exception as e:
            print(f"Error in subscribe_to_topics: {str(e)}")

    def on_message(self, client, userdata, message):
        try:
            print(f"\n[MESSAGE] Topic: {message.topic}")
            print(f"[MESSAGE] QoS: {message.qos}")
            
            # Parse JSON payload & pretty print the JSON document
            payload = json.loads(message.payload.decode())
            formatted_payload = json.dumps(payload, indent=2)
            print(f"[MESSAGE] Payload:\n{formatted_payload}")
                
        except json.JSONDecodeError as e:
            print(f"[ERROR] Invalid JSON payload: {str(e)}")
        except Exception as e:
            print(f"[ERROR] Error processing message: {str(e)}")


    def on_disconnect(self, client, userdata, rc):
        if rc != 0:
            print(f"Unexpected disconnection. RC: {rc}")
        else:
            print("Disconnected successfully")

    def on_subscribe(self, client, userdata, mid, granted_qos, properties=None):
        try:
            print(f"[SUBSCRIBE] Message ID: {mid}")
            print(f"[SUBSCRIBE] Granted QoS: {granted_qos}")
        except Exception as e:
            print(f"Error in on_subscribe: {str(e)}")

    def on_log(self, client, userdata, level, buf):
        print(f"[MQTT-LOG] {buf}")

    def test_publish(self, message="Test message"):
        """
        Method to test publishing to our subscribed topic
        """
        try:
            test_topic = f"client/{self.company_id}/test/result"
            result = self.mqtt_client.publish(
                topic=test_topic,
                payload=message,
                qos=self.config.get('qos', 1)
            )
            if result[0] == mqtt.MQTT_ERR_SUCCESS:
                print(f"Successfully published test message to {test_topic}")
            else:
                print(f"Failed to publish test message. Result: {result}")
        except Exception as e:
            print(f"Error publishing test message: {str(e)}")

    def run(self):
        print("Connecting to AWS IoT Core...")
        try:
            self.mqtt_client.connect(
                self.config['endpoint'],
                port=self.config.get('port', 8883),
                keepalive=self.config.get('keepalive', 60)
            )
            
            # Start the MQTT network loop
            self.mqtt_client.loop_forever()
            
        except KeyboardInterrupt:
            print("\nDisconnecting gracefully...")
            self.mqtt_client.disconnect()
        except Exception as e:
            print(f"Connection error: {str(e)}")
            raise

def main():
    client = AwsIotMqttClient()
    client.run()

if __name__ == "__main__":
    main()
