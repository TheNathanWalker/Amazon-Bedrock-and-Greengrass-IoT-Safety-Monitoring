import json
import base64
import boto3
import os
from datetime import datetime
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
bedrock_runtime = boto3.client('bedrock-runtime')
lambda_client = boto3.client('lambda')

PROMPT_TEXT ="""
You are an image analysis AI with specialization in workplace images. Your task is to analyze the provided image and provide the following information in JSON format, adhering to OSHA (Occupational Safety and Health Administration). You will identify hazards, safety violations, misplaced tools, and unsafe behavior.
 - "priority": A danger ranking integer, from 1 (low) to 5 (high) indicating the urgency or importance of addressing this analysis. 
 - "summary": A brief summary of the provided image
 - "description": A brief description of the item(s) or area(s) of concern.
 - "oshaReference": A reference to the relevant OSHA standard or regulation that may apply to the identified area of concern. 

Unless the image type is invalid, you must provide all four (4) fields: priority, summary, description, and oshaReference. 
 
Please ensure that your output is a valid JSON object and that all identified areas of concern are based on objective observations and in compliance with OSHA.

Review your work thoroughly to ensure that you're not tagging or flagging anything that does not exist within the image or that falls outside the scope of OSHA's jurisdiction.

If the provided image is does not depict a workplace or cannot be analyzed. You will complete the following 3 steps:
1: Provide a description of the image. 
2: Use the static text shown below for the fields "priority", "summary", and "oshaReference":
3: Return a JSON object with the following fields:
 - "priority": 0
 - "summary": "Invalid image"
 - "description": "The image appears to be ...."
 - "oshaReference": "N/A" 
"""

def extract_path_components(object_key):
    """Extract companyId and deviceId from S3 path"""
    parts = object_key.split('/')
    if len(parts) != 4:
        raise ValueError(f"Invalid path structure: {object_key}. Expected: company/companyId/deviceId/filename.jpg")
    return parts[1], parts[2]  # Return companyId, deviceId

def get_image_from_s3(bucket, key):
    """Retrieve and encode image from S3"""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        image_content = response['Body'].read()
        return base64.b64encode(image_content).decode('utf-8')
    except Exception as e:
        logger.error(f"Error retrieving image from S3: {str(e)}")
        raise

def normalize_analysis_data(raw_analysis):
    """Normalize the analysis data to the expected format"""
    try:
        logger.info(f"Normalizing analysis data: {json.dumps(raw_analysis, indent=2)}")
        
        # If description is a list, combine the concerns and references
        if isinstance(raw_analysis.get('description'), list):
            combined_description = ""
            combined_reference = ""
            
            for item in raw_analysis['description']:
                if combined_description:
                    combined_description += " "
                combined_description += item.get('concern', '')
                
                if combined_reference:
                    combined_reference += "; "
                combined_reference += item.get('oshaReference', '')
            
            normalized = {
                "priority": raw_analysis.get('priority'),
                "summary": raw_analysis.get('summary'),
                "description": combined_description,
                "oshaReference": combined_reference
            }
        else:
            # If it's already in the correct format, just ensure all fields exist
            normalized = {
                "priority": raw_analysis.get('priority'),
                "summary": raw_analysis.get('summary'),
                "description": raw_analysis.get('description', ''),
                "oshaReference": raw_analysis.get('oshaReference', '')
            }
        
        logger.info(f"Normalized analysis data: {json.dumps(normalized, indent=2)}")
        
        # Validate required fields
        required_fields = ['priority', 'summary', 'description', 'oshaReference']
        for field in required_fields:
            if not normalized.get(field):
                raise ValueError(f"Missing required field: {field}")
        
        return normalized
        
    except Exception as e:
        logger.error(f"Error normalizing analysis data: {str(e)}")
        raise

def analyze_image_with_bedrock(base64_image):
    try:        
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 64000,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64_image
                            }
                        },
                        {
                            "type": "text",
                            "text": PROMPT_TEXT
                        }
                    ]
                }
            ]
        })

        logger.info("Sending request to Bedrock")
        response = bedrock_runtime.invoke_model(
            # modelId="anthropic.claude-3-7-sonnet-20250219-v1:0",
            modelId="anthropic.claude-3-haiku-20240307-v1:0", # Old modelId
            body=body
        )
        
        response_body = json.loads(response['body'].read())
        logger.info(f"Raw response body: {json.dumps(response_body, indent=2)}")
        
        response_text = response_body['content'][0]['text']
        logger.info(f"Extracted text content: {response_text}")
        
        raw_analysis = json.loads(response_text)
        
        # Normalize the analysis data
        normalized_analysis = normalize_analysis_data(raw_analysis)
        
        return (
            normalized_analysis,
            response_body['usage']['input_tokens'],
            response_body['usage']['output_tokens']
        )
        
    except Exception as e:
        logger.error(f"Error in analyze_image_with_bedrock: {str(e)}")
        logger.error(f"Error type: {type(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise


def invoke_messenger_lambda(message):
    try:
        # Log the message we're about to send
        logger.info("=== START MESSENGER LAMBDA INVOCATION ===")
        logger.info(f"Sending message to messenger lambda: {json.dumps(message, indent=2)}")
        
        # Invoke the messenger lambda
        response = lambda_client.invoke(
            FunctionName='messenger-lambda',
            InvocationType='RequestResponse',
            Payload=json.dumps(message)
        )
        
        # Log the raw response
        status_code = response.get('StatusCode', 500)
        logger.info(f"Messenger lambda status code: {status_code}")
        # Read and decode the response payload
        response_payload = response['Payload'].read().decode('utf-8')
        logger.info(f"Raw messenger lambda response: {response_payload}")
        
        # Parse the response payload
        try:
            parsed_payload = json.loads(response_payload) if response_payload else {"status": "No response content"}
            logger.info(f"Parsed messenger lambda response: {json.dumps(parsed_payload, indent=2)}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse messenger lambda response: {str(e)}")
            parsed_payload = {"error": "Invalid JSON response"}
        
        result = {
            "statusCode": status_code,
            "payload": parsed_payload
        }
        
        logger.info(f"Final messenger lambda result: {json.dumps(result, indent=2)}")
        logger.info("=== END MESSENGER LAMBDA INVOCATION ===")
        
        return result
        
    except Exception as e:
        logger.error("=== MESSENGER LAMBDA ERROR ===")
        logger.error(f"Error invoking messenger lambda: {str(e)}")
        logger.error(f"Error type: {type(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return {
            "statusCode": 500,
            "payload": {
                "error": str(e)
            }
        }

def lambda_handler(event, context):
    try:
        logger.info("=== START LAMBDA HANDLER ===")
        
        # Extract S3 event details
        record = event['Records'][0]['s3']
        bucket = record['bucket']['name']
        object_key = record['object']['key']
        
        logger.info(f"Processing image from bucket: {bucket}, key: {object_key}")
        
        # Verify file extension
        if not object_key.lower().endswith('.jpg'):
            logger.info(f"Skipping non-jpg file: {object_key}")
            return
        
        # Get client and device IDs
        company_id, device_id = extract_path_components(object_key)
        logger.info(f"Extracted company_id: {company_id}, device_id: {device_id}")
        
        # Get image creation timestamp
        object_metadata = s3_client.head_object(Bucket=bucket, Key=object_key)
        timestamp = object_metadata['LastModified'].isoformat()
        
        # Get and encode image
        logger.info("Getting image from S3...")
        base64_image = get_image_from_s3(bucket, object_key)
        logger.info("Successfully encoded image to base64")
        
        # Analyze image with Bedrock
        logger.info("Analyzing image with Bedrock...")
        analysis_data, input_tokens, output_tokens = analyze_image_with_bedrock(base64_image)
        logger.info(f"Analysis completed. Analysis data: {json.dumps(analysis_data, indent=2)}")
        
        # Prepare message for messenger lambda
        message = {
            "analysis": analysis_data,
            "token_usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens
            },
            "requester": {
                "companyId": company_id,
                "deviceId": device_id,
                "timestamp": timestamp
            }
        }
        
        # Log the prepared message
        logger.info(f"Prepared message for messenger lambda: {json.dumps(message, indent=2)}")
        
        # Send to messenger lambda
        logger.info("=== INVOKING MESSENGER LAMBDA ===")
        messenger_response = invoke_messenger_lambda(message)
        logger.info("=== MESSENGER LAMBDA INVOCATION COMPLETE ===")
        
        # Prepare the final response
        response = {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Analysis complete",
                "analysis": analysis_data,
                "messenger_response": messenger_response
            })
        }
        
        logger.info(f"Final response: {json.dumps(response, indent=2)}")
        logger.info("=== END LAMBDA HANDLER ===")
        
        return response
        
    except Exception as e:
        logger.error("=== LAMBDA HANDLER ERROR ===")
        logger.error(f"Error processing image: {str(e)}")
        logger.error(f"Error type: {type(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e)
            })
        }