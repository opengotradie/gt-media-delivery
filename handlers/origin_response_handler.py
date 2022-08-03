
redirection_rules_map = {'images-100x100': 'images',  'profile-70x70': 'profile'}

HTTP_STATUS_FORBIDDEN = '403'
HTTP_STATUS_MOVED = '301'
HTTP_STATUS_SUCCESS = '200'
HTTP_METHOD_OPTIONS = 'OPTIONS'

def handle(event, context):    
    response = event["Records"][0]["cf"]["response"] 
    request = event["Records"][0]["cf"]["request"]
    response_headers = response["headers"] 
    status = response["status"]
    uri = request['uri']
    if status == HTTP_STATUS_FORBIDDEN:
        print(status)
        response_headers['Cache-Control']  = [{'key': 'Cache-Control', 'value': 'max-age=1'}] 
        uri_parts = uri.split("/", 2)
        key_prefix = uri_parts[1]
        key_suffix = uri_parts[2]
        redirection_prefix = redirection_rules_map.get(key_prefix)
        if redirection_prefix:
            print('redirecting')
            redirect_uri = f'/{redirection_prefix}/{key_suffix}'
            response['status'] = HTTP_STATUS_MOVED
            response['headers']['location'] = [{ 'key': 'Location', 'value':redirect_uri}] 
            return response        
    if request['method'] == HTTP_METHOD_OPTIONS:
        response['status'] = HTTP_STATUS_SUCCESS
        response['statusDescription'] = 'Success'
        response['body'] = 'Success'
    return response
    