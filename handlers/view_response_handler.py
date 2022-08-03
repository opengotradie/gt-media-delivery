

def handle(event, context):    
    response = event["Records"][0]["cf"]["response"]
    request = event["Records"][0]["cf"]["request"]
    response_headers = response["headers"]          
   
    if not response_headers.get('access-control-allow-origin') :
        response_headers['Access-Control-Allow-Origin']  = [{'key': 'Access-Control-Allow-Origin', 'value': '*'}]
    if not response_headers.get('access-control-expose-headers') :
        response_headers['Access-Control-Expose-Headers']  = [{'key': 'Access-Control-Expose-Headers', 'value': '*'}]
    if not response_headers.get('access-control-allow-methods') :
        response_headers['Access-Control-Allow-Methods']  = [{'key': 'Access-Control-Allow-Methods', 'value': 'GET,PUT'}]
    if not response_headers.get('access-control-allow-headers') :
        response_headers['Access-Control-Allow-Headers']  = [{'key': 'Access-Control-Allow-Headers', 'value': '*'}]

    if request['method'] == 'OPTIONS':
        response['status'] = '200'
        response['statusDescription'] = 'Success'
        response['body'] = 'Success'
    return response