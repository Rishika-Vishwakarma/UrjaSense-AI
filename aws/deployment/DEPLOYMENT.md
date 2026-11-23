# AWS deployment guide (reference configuration)

> **Status: not deployed.** Nothing in this repository has been deployed to, or tested against, a live AWS
> account. The app runs locally (see the root README). This folder gives a modular, reviewable AWS setup.

| Service | Role | File |
|---|---|---|
| Amazon API Gateway (HTTP API) | Public API, throttling, CORS | `template.yaml`, `../api_gateway/openapi.yaml` |
| AWS Lambda | Flask API (`api_handler`), prediction (`predict_handler`), SNS fan-out (`notify_handler`) | `../lambda/` |
| Amazon RDS for MySQL | Primary database (private subnets, encrypted) | `template.yaml` |
| Amazon SNS | Optional SMS/email channel (`SNS_ENABLED=1`) | `../sns_publisher.py` |
| Amazon S3 (+CloudFront) | Static frontend hosting | `template.yaml` (bucket only) |
| Amazon CloudWatch | Lambda/RDS alarms, Lambda logs | `template.yaml` |

## Steps
1. `pip install apig-wsgi` and add it to `requirements.txt` for the Lambda package.
2. Create the DB schema once from a host that can reach RDS (bastion / Cloud9 in the VPC):
   `DB_HOST=<endpoint> DB_USER=urjaadmin DB_PASSWORD=... LOAD_SAMPLE_DATA=0 python -m database.database_config`
3. `sam build -t aws/deployment/template.yaml && sam deploy --guided` (supply SecretKey, DbPassword, VPC, subnets).
4. The Lambda in a VPC needs outbound access for SNS (NAT gateway or VPC endpoint).
5. Upload `frontend/` to the S3 bucket, put CloudFront + ACM (HTTPS) in front, and set
   `window.URJA_API_BASE = "https://<api-id>.execute-api.<region>.amazonaws.com"` before `js/main.js` in each HTML page.
6. In-memory rate limiting is per Lambda instance; rely on API Gateway throttling (set in the template) in AWS.
7. scikit-learn + pandas exceed the Lambda zip limit: deploy `ApiFunction` as a container image or use a Lambda layer.

Secrets: use AWS Secrets Manager / SSM Parameter Store in production instead of plain parameters.
