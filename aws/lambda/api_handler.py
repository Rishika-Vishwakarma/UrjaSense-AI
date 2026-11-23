"""AWS Lambda entry point: runs the Flask API behind Amazon API Gateway (HTTP API, payload v2).

Uses the `apig-wsgi` adapter. NOT deployed or tested against a live AWS account
in this repository; see aws/deployment/DEPLOYMENT.md.
"""
from apig_wsgi import make_lambda_handler

from backend.app import create_app

_app = create_app()
handler = make_lambda_handler(_app, binary_support=False)
