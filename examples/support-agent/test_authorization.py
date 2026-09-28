"""Run against the deployed revision, with both test identities provisioned."""
import os
import httpx

def test_cross_customer_denied():
    base=os.environ['SUPPORT_BASE_URL'].rstrip('/')
    record_id=os.getenv('TENANT_B_RECORD_ID','2')
    headers_a={'Authorization':'Bearer '+os.environ['TENANT_A_TOKEN']}
    headers_b={'Authorization':'Bearer '+os.environ['TENANT_B_TOKEN']}
    # If Cloud Run requires IAM, use a separate platform authorization header.
    if os.getenv('SUPPORT_IDENTITY_TOKEN'):
        headers_a['X-Serverless-Authorization']='Bearer '+os.environ['SUPPORT_IDENTITY_TOKEN']
        headers_b['X-Serverless-Authorization']='Bearer '+os.environ['SUPPORT_IDENTITY_TOKEN']
    with httpx.Client(timeout=30,follow_redirects=False,trust_env=os.getenv("SUPPORT_TEST_TRUST_ENV","false").lower()=="true") as client:
        own=client.get(f'{base}/records/{record_id}',headers=headers_b)
        assert own.status_code==200, 'Test setup must prove the other customer record exists and is accessible to its owner'
        denied=client.post(f'{base}/records/{record_id}',headers=headers_a,json={'body':own.json()['body']})
        assert denied.status_code==403, f'Cross-customer update must be denied, received {denied.status_code}'
