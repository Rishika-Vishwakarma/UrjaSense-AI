"""Amazon SNS notification publisher (optional, modular).

Does nothing unless SNS_ENABLED=1, SNS_TOPIC_ARN is set and boto3 can find AWS
credentials. Failure never breaks the main request: in-app notifications in
MySQL are the source of truth; SNS is an extra delivery channel (SMS/email).
"""
import logging

log = logging.getLogger("urjasense.sns")


def publish(config, subject: str, message: str) -> bool:
    if not config.get("SNS_ENABLED") or not config.get("SNS_TOPIC_ARN"):
        return False
    try:
        import boto3
        boto3.client("sns", region_name=config["AWS_REGION"]).publish(
            TopicArn=config["SNS_TOPIC_ARN"], Subject=subject[:100], Message=message)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("SNS publish failed: %s", exc)
        return False
