
redirection_rules_map = {'images-100x107': 'images', 'images-123x173': 'images', 'images-124x124': 'images', 'images-126x98': 'images',
 'images-151x107': 'images', 'images-163x277': 'images', 'images-168x235': 'images', 'images-255x95': 'images',
 'images-305x186': 'images', 'images-375x666': 'images', 'images-52x52': 'images', 'images-79x134': 'images',
 'images-83x95': 'images', 'profile-150x150': 'profile', 'profile-20x20': 'profile', 'profile-30x30': 'profile',
 'profile-50x50': 'profile', 'profile-58x58': 'profile', 'profile-70x70': 'profile'}

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
    