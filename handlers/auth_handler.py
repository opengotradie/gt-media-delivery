import boto3

cognito_client = boto3.client('cognito-idp', region_name='ap-southeast-2')
PREFIX = 'Bearer'
UNAUTHORIZED_RESPONSE = {'status': '401','statusDescription': 'Unauthorized'}
HTTP_METHOD_OPTIONS = 'OPTIONS'

def auth(event, context):
    request = event["Records"][0]["cf"]["request"]    
    request_headers = request["headers"]
    auth_header = request_headers.get('authorization')
    
    try:
        if request['method'] == HTTP_METHOD_OPTIONS:
            return request
        if auth_header:
            auth_header_value = auth_header[0].get('value')
            bearer,_, token = auth_header_value.partition(' ')
            if(bearer != PREFIX):
                return UNAUTHORIZED_RESPONSE
            else:
                response = cognito_client.get_user(AccessToken=token)                
                if response and isinstance(response, dict):
                    return request
                else:
                    return UNAUTHORIZED_RESPONSE                
        else:            
            return UNAUTHORIZED_RESPONSE
        
    except Exception as exc:
        return UNAUTHORIZED_RESPONSE
    