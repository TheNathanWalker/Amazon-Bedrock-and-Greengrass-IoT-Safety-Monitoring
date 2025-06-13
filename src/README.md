This page contains the recommendations to deploy the code into your AWS account and your Greengrass v2 device. In the next major code release, a CloudFormation template will be supplied. 

The hardware to run this code is minimal. You will need a device capabable of running Greengrass v2 and an RTSP camera that can be accessed by your Greengrass device. It is assumed that your target edge device has the Greengrass runtime properly configured. The install process is fully documented in the [AWS IoT Greengrass documentation](https://docs.aws.amazon.com/greengrass/v2/developerguide/install-greengrass-core-v2.html)

As a reminder, there are four main code elements in this solution design:

1. [Greengrass V2 analyze component](../src/analyze-component/)
2. [Bedrock Lambda](../src/lambda/bedrock-lambda.py)
3. [Messenger Lambda](../src/lambda/messenger-lambda.py)
4. [Greengrass V2 result component](../src/result-component) (optional)
5. [MQTT Monitor Client](../src/mqtt-admin-client/mqtt-monitor-client.py) (optional)

The first three are mandatory for this solution to work. 

The result component and MQTT monitor are not required. These result component simply subscribes to the device specific topic to receive, log, and locally act upon the results of the Bedrock safety image analysis. 

The MQTT monitor client displays all MQTT messages for a particular companyId. 

## Greengrass IoT Thing Policy

Before installing the components, you are advised to customize the default [GreengrassV2IoTThingPolicy](https://docs.aws.amazon.com/greengrass/v2/developerguide/device-auth.html) which is used to define the authentication and authorization for your AWS IoT Greengrass device. Following the principle of least priviledge, you should employ policy with minimal access. For development and testing, the following custom GreengrassV2IoTThingPolicy was used for minimal permissions. 

```
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "iot:Connect",
        "iot:Subscribe",
        "greengrass:*"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Publish",
      "Resource": [
        "arn:aws:iot:*:*:$aws/things/${iot:Connection.Thing.ThingName}/#"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "iot:Receive",
      "Resource": [
        "arn:aws:iot:*:*:topic/client/${iot:Connection.Thing.Attributes[companyId]}/${iot:Connection.Thing.ThingName}/cmd",
        "arn:aws:iot:*:*:topic/client/${iot:Connection.Thing.Attributes[companyId]}/${iot:Connection.Thing.ThingName}/result",
        "arn:aws:iot:*:*:topic/$aws/things/${iot:Connection.Thing.ThingName}/#",
        "arn:aws:iot:*:*:*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::YOUR-IMAGE-BUCKET/company/${iot:Connection.Thing.Attributes[companyId]}/${iot:Connection.Thing.Attributes[deviceId]}/*"
    }
  ]
}
```

There is no need to modify the Token Exchange Service (TES) policy, as this is used to enable the core device to obtain temporary credentials for accessing other AWS services. 

## Analyze Component 
This code element is deployed as a standard Greengrass V2 component. It can has been tested as a local deployment as well as an IoT core component. Refer to the [AWS IoT Greengrass documentation](https://docs.aws.amazon.com/greengrass/v2/developerguide/greengrass-components.html) to help you develop, deploy, and manage your components. 

An AWS Greengrass v2 component requires two basic elements: the component recipe and the component artifacts. The component recipe is a JSON or yaml file that defines how the component is the blueprint to define how Greengrass manages the component deplloyment, dependencies, execution and access to external resources. The analyze component recipe is [here](../src/analyze-component/recipe-analyze.json). You will need to adapt this recipe to your use case. 

Next you will prepare the component artifacts. In this case it is the [analyze component code](../src/analyze-component/analyze.py) and the [requirements.txt](../src/analyze-component/requirements.txt). 


### Analyze Component Artifacts

Zip the Python code and the pip3 requirements.txt file in a flat zip file. e,g. `zip -j ./analyze.zip ./code/component/analyze/1.0.0/analyze.py ./code/component/analyze/1.0.0/requirements.txt`. Next upload the zip file to your S3 bucket. The S3 zip file's path and name must match the Manifests.Artifacts.URI in the JSON recipe file. 
```
"Artifacts": [
    {
        "URI": "s3://YOUR-ARTIFACT-BUCKET/analyze.zip",
        "Unarchive": "ZIP"
    }
]
```

Next create a component in the AWS IoT console and deploy it to your target device(s). Ensure each Greengrass thing has the required attributres. The `clientId`, `deviceId`, and `rtspUrl` are used by the component code. Each device uploads its JPG images for analysis to its own company and device prefix. If the RTSP device requires authentication, you can include the details in the RTSP URL attribute. The general formatting if the URL is of the form, `rtsp://[username:password@]ip_address[:rtsp_port]/server_URL[[?param1=val1[?param2=val2]…[?paramN=valN]]`. The exact URL depends upon the device manufacturer. Refer to your camera vendor documentaiton. A simple SV3C camera was used to develop and test this code. 

The next version of code will follow best practices to store the camera credentials in AWS Secrets Manager. 

```
aws iot describe-thing --thing-name 9971
{
    "defaultClientId": "9971",
    "thingName": "9971",
    "thingId": "43e64323-f226-4fe2-afe4-b91b4cc012c1",
    "thingArn": "arn:aws:iot:us-east-1:YOUR-AWS-ACCOUNT:thing/9971",
    "attributes": {
        "clientId": "client-3985",
        "deviceId": "device-001",
        "rtspUrl": "rtsp://10.10.11.1:554/stream0",
        "s3Bucket": "YOUR-IMAGE-BUCKET"
    },
    "version": 3
}
```

When the component has been deployed, you will note a line similar to the following in the greeengrass.log file. 

```
2025-04-09T17:11:17.204Z [INFO] (AwsEventLoop 2) com.aws.greengrass.deployment.IotJobsHelper: Job status update was accepted. {Status=SUCCEEDED, ThingName=9971, JobId=f765e0aa-f6f7-43f1-a20f-68f074b0d96d}
```

Additionally, the component log will capture details about the dependency installation and initialization. After the component completes the run script, you will observe log entries similar to the following: 

```
2025-04-09T17:11:05.888Z [INFO] (pool-3-thread-18) analyze: shell-runner-start. {scriptName=services.analyze.lifecycle.Run.Script, serviceName=analyze, currentState=STARTING, command=["cd /greengrass/v2/packages/artifacts-unarchived/analyze/1.0.2/analyze\n. venv/b..."]}
2025-04-09T17:11:06.795Z [INFO] (Copier) analyze: stdout. INFO:__main__:Starting MQTT Subscriber Component. {scriptName=services.analyze.lifecycle.Run.Script, serviceName=analyze, currentState=RUNNING}
2025-04-09T17:11:06.802Z [INFO] (Copier) analyze: stdout. INFO:awsiot.eventstreamrpc:<Connection at 0x7f8e545e90 /greengrass/v2/ipc.socket:0> connected. {scriptName=services.analyze.lifecycle.Run.Script, serviceName=analyze, currentState=RUNNING}
2025-04-09T17:11:06.804Z [INFO] (Copier) analyze: stdout. INFO:__main__:Retrieved thing name: 9971. {scriptName=services.analyze.lifecycle.Run.Script, serviceName=analyze, currentState=RUNNING}
2025-04-09T17:11:06.805Z [INFO] (Copier) analyze: stdout. INFO:__main__:AWS Container Credentials URI is configured. {scriptName=services.analyze.lifecycle.Run.Script, serviceName=analyze, currentState=RUNNING}
2025-04-09T17:11:06.854Z [INFO] (Copier) analyze: stdout. INFO:botocore.credentials:Found credentials in shared credentials file: ~/.aws/credentials. {scriptName=services.analyze.lifecycle.Run.Script, serviceName=analyze, currentState=RUNNING}
2025-04-09T17:11:07.574Z [INFO] (Copier) analyze: stdout. INFO:__main__:Successfully constructed topic: client/client-3985/device-001/cmd. {scriptName=services.analyze.lifecycle.Run.Script, serviceName=analyze, currentState=RUNNING}
2025-04-09T17:11:07.582Z [INFO] (Copier) analyze: stdout. INFO:awsiot.eventstreamrpc:<Connection at 0x7f85f60050 /greengrass/v2/ipc.socket:0> connected. {scriptName=services.analyze.lifecycle.Run.Script, serviceName=analyze, currentState=RUNNING}
2025-04-09T17:11:07.692Z [INFO] (Copier) analyze: stdout. INFO:__main__:Successfully subscribed to topic: client/client-3985/device-001/cmd. {scriptName=services.analyze.lifecycle.Run.Script, serviceName=analyze, currentState=RUNNING}
```

The last line tells us that the component was deployed, the lifecycle run script has started, and the deployed Greengrass component has subscribed to its command topic. Note the exact topic name corresponds to device attributes. 

## S3 Preparation
The bucket where the images will be sent is set in the MQTTSubscriber class of the analyze component. `self.s3_bucket = "YOUR-IMAGE-BUCKET"`. The S3 bucket must be in the same region as your IoT devices. 

Create an bucket trigger for the Bedrock Lambda function via the CLI or console. Using the AWS CLI, your command will be similar to the following. 

```
aws s3api put-bucket-notification-configuration \
  --bucket YOUR-IMAGE-BUCKET \
  --notification-configuration '{
    "LambdaFunctionConfigurations": [{
      "LambdaFunctionArn": "arn:aws:lambda:region:account-id:function:bedrock-lambda",
      "Events": ["s3:ObjectCreated:*"]
    }]
  }'
```

## Bedrock Lambda

The Bedrock lambda is deployed in a Python 3.12 runtime environment. Becauase the code does not have any hardware dependencies, such as JNI, it can run with either x86_64 or the arm64 architecture. In the spirit of frugality, consider using Graviton instances. 

The code has not been observed to consume more than about 100MB in Lambda testing. Evaluation in a test environment will confirm if 128MB is sufficient for the code to execute properly. Larger images may require you to adjust the max_tokens in the Bedrock prompt body of the Bedrock Lambda code. 

The Bedrock Lambda needs certain permission to operate properly. 
1. Retrieve the JPG that was uploaded from Greengrass
2. Invoke the desired Bedrock LLM
3. Invoke the Messenger Lambda
4. CloudWatch and other observability features. 

```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject"
            ],
            "Resource": "arn:aws:s3:::YOUR-IMAGE-BUCKET/*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel"
            ],
            "Resource": "arn:aws:bedrock:YOUR-AWS_REGION:YOUR-AWS-ACCOUNT:foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
        },
        {
            "Effect": "Allow",
            "Action": [
                "lambda:InvokeFunction"
            ],
            "Resource": "arn:aws:lambda:YOUR-AWS_REGION:YOUR-AWS-ACCOUNT:function:messenger-lambda"
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "*"
        }
    ]
}
```

Ensure your account has been configured for access to the target Bedrock model. The next release of this code will use a more recent Claude model on Bedrock. The current release is hard coded for anthropic.claude-3-haiku-20240307-v1:0. 

## Messenger Lambda

The Messenger Lambda does not invoke Bedrock. It simply takes the results from the Bedrock Lambda and acts according to your business logic. The messenger Lambda in this repository is fairly simple. It passes the results to an IoT core topic. You can augment this Lambda to align with your business requirements. For example, you could store image analysis results in a time series database. Results higher than a particular threshold could be sent to an SNS topic for proper notification. 

The code for this Lambda has also been tested to use the Python 3.12 runtime. During development, the CloudWatch logs indiated memory use never exceeded 50MB.

The functionality of the Messenger Lambda will direct the permissions you list in the Lambda role. If you are simply passing the results to IoT core, your policy may look similar to the following: 

```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "iot:DescribeEndpoint",
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": "iot:Publish",
            "Resource": "arn:aws:iot:YOUR-AWS_REGION:YOUR-AWS-ACCOUNT:topic/client/*"
        }
    ]
}
```

## Result Component

The result component is designed to subscribe to the result topic, log the analysis, and optionally take action on the local device. This code was tested on a Raspberry Pi with a SenseHat. Due to some known bugs with the Sense Python library, the component is unable to display the numerical result priority code on the LED panel. 

The component creation and deployment are similar to the Analyze Component. You may choose to not deploy this component, instead opting to subscribe to the result topics from a mobile application for all greengrass devices and their associated cameras for a particular companyId. 

## Result Component with Sense Hat Integration

Also found in this repository is the [result-sensehat.py](../src/result-component/result-sensehat.py) Greengrass v2 component code. This code is intended to parse the incoming MQTT topic message and change the Sense Hat display according to the severity level. Unfortunately, this code seems to have hit a known bug with the RTMIU, Real-Time Inertial Measurement Unit. While the required packages have been installed, I was unable to resovle this error, even after following the steps in https://github.com/RPi-Distro/RTIMULib/. Although this is a not a core functionality bug, I will continue to work to resolve this for a later code release. 

Until this is resolved, you are advised to use the provided result.py. 

```
2025-04-17T16:31:54.753Z [INFO] (Copier) result: stdout. from sense_hat import SenseHat. {scriptName=services.result.lifecycle.Run.Script, serviceName=result, currentState=RUNNING}
2025-04-17T16:31:54.753Z [INFO] (Copier) result: stdout. File "/greengrass/v2/packages/artifacts-unarchived/result/1.0.5/result/venv/lib/python3.11/site-packages/sense_hat/__init__.py", line 2, in <module>. {scriptName=services.result.lifecycle.Run.Script, serviceName=result, currentState=RUNNING}
2025-04-17T16:31:54.754Z [INFO] (Copier) result: stdout. from .sense_hat import SenseHat, SenseHat as AstroPi. {scriptName=services.result.lifecycle.Run.Script, serviceName=result, currentState=RUNNING}
2025-04-17T16:31:54.754Z [INFO] (Copier) result: stdout. File "/greengrass/v2/packages/artifacts-unarchived/result/1.0.5/result/venv/lib/python3.11/site-packages/sense_hat/sense_hat.py", line 11, in <module>. {scriptName=services.result.lifecycle.Run.Script, serviceName=result, currentState=RUNNING}
2025-04-17T16:31:54.754Z [INFO] (Copier) result: stdout. import RTIMU  # custom version. {scriptName=services.result.lifecycle.Run.Script, serviceName=result, currentState=RUNNING}
2025-04-17T16:31:54.755Z [INFO] (Copier) result: stdout. ^^^^^^^^^^^^. {scriptName=services.result.lifecycle.Run.Script, serviceName=result, currentState=RUNNING}
2025-04-17T16:31:54.755Z [INFO] (Copier) result: stdout. ModuleNotFoundError: No module named 'RTIMU'. {scriptName=services.result.lifecycle.Run.Script, serviceName=result, currentState=RUNNING}
2025-04-17T16:31:54.931Z [INFO] (Copier) result: Run script exited. {exitCode=1, serviceName=result, currentState=RUNNING}
```

```
(venv) root@raspberrypi:/greengrass/v2/logs# dpkg -l |egrep -i 'sense|rtimu'
ii  librtimulib-dev                                  7.2.1-6+bookworm                          arm64        Versatile C++ and Python 9-dof, 10-dof and 11-dof IMU library (dev files)
ii  librtimulib-utils                                7.2.1-6+bookworm                          arm64        Versatile C++ and Python 9-dof, 10-dof and 11-dof IMU library (utilities)
ii  librtimulib7                                     7.2.1-6+bookworm                          arm64        Versatile C++ and Python 9-dof, 10-dof and 11-dof IMU library (shared library)
ii  python3-rtimulib                                 7.2.1-6+bookworm                          arm64        Versatile C++ and Python 9-dof, 10-dof and 11-dof IMU library (Python 3)
ii  python3-sense-hat                                2.6.0-1                                   all          Sense HAT python library (Python 3)
ii  sense-hat                                        1.4                                       all          Sense HAT configuration, libraries and examples
```

