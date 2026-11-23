"""Standalone Lambda: fan-out an incident notification to the Amazon SNS topic (SMS/email subscribers).

Event: {"subject": "...", "message": "..."}.  Env: SNS_TOPIC_ARN.
The web app already stores in-app notifications in MySQL; this is the optional extra channel.
"""
import json
import os

import boto3

_sns = boto3.client("sns")


def handler(event, _context):
    topic = os.environ["SNS_TOPIC_ARN"]
    if not event.get("message"):
        return {"statusCode": 400, "body": json.dumps({"error": "message required"})}
    res = _sns.publish(TopicArn=topic, Subject=str(event.get("subject", "UrjaSense AI update"))[:100], Message=event["message"])
    return {"statusCode": 200, "body": json.dumps({"message_id": res["MessageId"]})}
