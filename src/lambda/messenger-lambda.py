import boto3
import json
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def validate_message(analysis_results):
    """Validate the incoming message structure"""
    required_fields = {
        'analysis': ['priority', 'summary', 'description', 'oshaReference'],
        'token_usage': ['input_tokens', 'output_tokens', 'total_tokens'],
        'requester': ['companyId', 'deviceId', 'timestamp']
    }
    
    for section, fields in required_fields.items():
        if section not in analysis_results:
            raise KeyError(f"Missing section: {section}")
        for field in fields:
            if field not in analysis_results[section]:
                raise KeyError(f"Missing field {field} in {section}")

def lambda_handler(event, context):
    try:
        # Log incoming event
        logger.info(f"Received event: {json.dumps(event, indent=2)}")
        
        # Validate message structure
        validate_message(event)
        
        # Extract client and device IDs from the requester object
        company_id = event['requester']['companyId']
        device_id = event['requester']['deviceId']
        
        # Initialize IoT client
        iot = boto3.client('iot')
        endpoint = iot.describe_endpoint(endpointType='iot:Data-ATS')['endpointAddress']
        
        # Initialize IoT data client with endpoint
        iot_data = boto3.client('iot-data', 
                              endpoint_url=f'https://{endpoint}')
        
        # Construct the topic string
        topic = f'client/{company_id}/{device_id}/result'
        
        # Convert dict to JSON string
        message = json.dumps(event)
        
        logger.info(f"Publishing to topic: {topic}")
        logger.info(f"Message: {message}")
        
        # Publish to IoT Core topic
        response = iot_data.publish(
            topic=topic,
            qos=1,
            payload=message
        )
        
        return {
            'statusCode': 200,
            'body': 'Successfully published to IoT Core'
        }
        
    except KeyError as e:
        error_msg = f'Error: Missing required field in analysis results: {str(e)}'
        logger.error(error_msg)
        return {
            'statusCode': 400,
            'body': error_msg
        }
    except Exception as e:
        error_msg = f'Error publishing to IoT Core: {str(e)}'
        logger.error(error_msg)
        return {
            'statusCode': 500,
            'body': error_msg
        }
