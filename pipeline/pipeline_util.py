import os
import boto3
import hashlib
import json
from time import sleep
from copy import deepcopy
from random import randint

def get_cfn_client():
    return boto3.client('cloudformation')

def get_s3_resource():
    return boto3.resource('s3')

def get_apigw_client():
    return boto3.client('apigateway')

def get_code_bucket(branch_name):
    if branch_name == 'master':
        return f'temp-media-delivery-code-bucket-{branch_name}' 
    else:
        return f'temp-media-delivery-code-bucket-{branch_name}-branch'

def query_cfn_output_from_stackout(stack_details, outputkey):
    if 'Outputs' not in stack_details['Stacks'][0]:
        raise Exception('No outputs available in the stack')
    outputs = stack_details['Stacks'][0]['Outputs']
    output = list(filter(lambda o: o['OutputKey']== outputkey, outputs))
    return output[0]['OutputValue'] if output else None

def get_stack_details(stack_name, retries=0):
    cfn_client = get_cfn_client()
    try:
        stack_details = cfn_client.describe_stacks(
           StackName=stack_name 
        )
        return stack_details
    except Exception as exp:
        print(exp)
        if retries < 5:
            retries+=1
            sleep(5)
            return get_stack_details(stack_name, retries=retries)
        raise exp

def query_cfn_output(stack_name, outputkey):
    stack_details = get_stack_details(stack_name)
    return query_cfn_output_from_stackout(stack_details, outputkey)

def get_main_stack_name(branch_name):
    if branch_name == 'main':
        return f'public-media-delivery-{branch_name}' 
    else:
        return f'public-media-delivery-{branch_name}-branch'

def get_api_endpoint(api_gw_stack_name, branch):
    stack_resources = get_stack_resources(api_gw_stack_name)
    api_resource = list(
        filter(
            lambda x:x.get('LogicalResourceId') == 'GTAPIGateway',
            stack_resources
        )
    )
    if len(api_resource):
        api_resource = api_resource[0]
        api_id = api_resource.get('PhysicalResourceId')
        if not api_id:
            return None
        return f'https://{api_id}.execute-api.us-east-1.amazonaws.com/v1-{branch}'
    return None

def generate_variables_map(stack_name):
    packaged_variables_map = {}
    variables_map = {}
    branch = None
    stack_resources = get_stack_resources(stack_name)
    for res in stack_resources:
        category, branch_name, variables = filter_candidate_outputs(res)
        if branch_name:
            branch = branch_name
        if category and variables:
            variables_map[category] = variables
    packaged_variables_map['branch'] = branch
    packaged_variables_map['data'] = variables_map
    return packaged_variables_map

def filter_candidate_outputs(res):
    arn = res.get('PhysicalResourceId')
    end_index = arn.rindex('/')
    arn_first_part = arn[:end_index]
    start_index = arn_first_part.rindex('/')
    nested_stack_name = arn_first_part[start_index + 1 :]
    stack_details = get_stack_details(nested_stack_name)
    tags = stack_details.get('Stacks')[0].get('Tags')
    if tags and isinstance(tags, list) and len(tags) > 0:
        gt_stack_name_candidate = list(
            filter(
                lambda x: x.get('Key') == 'GTStackName',
                tags
            )
        )
        branch_name_candidate = list(
            filter(
                lambda x: x.get('Key') == 'Branch',
                tags
            )
        )
        branch_name = branch_name_candidate[0].get('Value') if branch_name_candidate else None
        if gt_stack_name_candidate and len(gt_stack_name_candidate) > 0:
            return gt_stack_name_candidate[0].get('Value'), branch_name, generate_output_map(stack_details)
    return None, None, None

def get_stack_resources(stack_name):
    cfn_client = get_cfn_client()
    try:
        stack_resources = cfn_client.list_stack_resources(
           StackName=stack_name 
        )
        return stack_resources.get('StackResourceSummaries')
    except Exception as exp:
        print(exp)
        raise exp

def generate_output_map(stack_details):
    output_map = {}
    temp_array = stack_details['Stacks'][0]['Outputs']
    contents = deepcopy(temp_array)
    for item in temp_array:
        key = item['OutputKey']
        if key.endswith('LambdaArn'):
            arn_value = item['OutputValue']
            default_region = 'us-east-2'
            contents.append({
                'OutputKey' : f'{key}URI',
                'OutputValue': f'arn:aws:apigateway:{default_region}:lambda:path/2015-03-31/functions/{arn_value}/invocations'
            })
    for con in contents:
        output_map[con['OutputKey']] = con['OutputValue']
    return output_map

def load_variables_from_file(swagger_var_filename):
    variables_content = open(f'pipeline/api/{swagger_var_filename}', 'r').read()
    variables_json = json.loads(variables_content)
    return variables_json

def generate_variables_dict():
    return {
            **load_variables_from_file('swagger_commons.json'), 
            **load_variables_from_file('swagger_models.json')
        }

def generate_mustache_var_map(stack_details):
    mustache_var_map = generate_output_map(stack_details)
    return load_mustache_properties(mustache_var_map)

def load_mustache_properties(mustache_var_map):
    all_properties = json.load(open('pipeline/mustache_properties.json', 'rb'))
    environment = os.getenv('PIPELINE_DEFAULT_BRANCH', 'dev')
    mustache_variables = all_properties.get(environment)
    return {**mustache_var_map, **mustache_variables}

def resolve_references(raw_swagger):
    swagger_variables_dict = generate_variables_dict()
    raw_swagger_json = json.loads(raw_swagger)
    apply_references(raw_swagger_json,deepcopy(raw_swagger_json), swagger_variables_dict)
    return raw_swagger_json

def apply_references(source, overrides, var_dict):
    for key, value in overrides.items():
        if isinstance(value, str) and "#REF::" in value:
            replacable_variable = value[6:]
            if replacable_variable in var_dict:
                source[key] = var_dict[replacable_variable]
            else:
                raise Exception(f'Invalid Reference Request ::{value}')
        elif isinstance(value, dict) and value:
            returned = apply_references(source.get(key, {}), value, var_dict)
            source[key] = returned
        elif isinstance(value, list):
            resolved_array = apply_references_to_list(value, var_dict)
            source[key] = resolved_array
        else:
            source[key] = overrides[key]
    return source

def apply_references_to_list(list_obj, var_dict):
    resolved_array = []
    for item in list_obj:
        if isinstance(item, dict):
            resolved_array.append(apply_references(item, deepcopy(item), var_dict))
        else:
            resolved_array.append(item)
    return resolved_array

def get_current_git_branch():
    default_branch = os.getenv('PIPELINE_DEFAULT_BRANCH')
    if default_branch:
        return default_branch
    repo_name = os.popen('bash pipeline/codebuild_branch.sh').read()
    if repo_name.strip().lower() == 'head':
        repo_name = os.popen("git log -1 --pretty=format:'%d'").read()
        repo_name = repo_name[repo_name.rfind(',')+2:-1]
        if 'origin' in repo_name:
            repo_name = repo_name[7:]
    if not repo_name:
        repo_name = f'pr-{randint(0,10)}-{randint(0,10)}-{randint(0,10)}'
    repo_name = repo_name.replace('\n','').lower()
    pr_prefix = os.getenv('PR_PREFIX')
    if pr_prefix:
        return f'{repo_name}-{pr_prefix}'
    else:
        return repo_name

def get_last_commit_author():
    author = os.popen("git log -1 --pretty=format:'%ae'").read()
    return author.replace('\n','').replace('@','-').replace('.','').replace('_','').lower()

def update_cfn_stack(stack_name, current_branch, cfn_code=None, cfn_location=None, parameters=[]):
    print(f'Updating {stack_name} stack')
    cfn_client = get_cfn_client()
    try:
        if cfn_code:
            cfn_client.update_stack(
                StackName=stack_name,
                TemplateBody=cfn_code,
                Parameters=parameters,
                Capabilities=['CAPABILITY_IAM','CAPABILITY_AUTO_EXPAND'],
                Tags=[{'Key':'branch', 'Value': current_branch.replace('-','')}]
            )
        elif cfn_location:
            print(cfn_location)
            cfn_client.update_stack(
                StackName=stack_name,
                TemplateURL=cfn_location,
                Parameters=parameters,
                Capabilities=['CAPABILITY_IAM','CAPABILITY_AUTO_EXPAND'],
                Tags=[{'Key':'branch', 'Value': current_branch.replace('-','')}]
            )
        waiter = cfn_client.get_waiter('stack_update_complete')
        waiter.wait(StackName=stack_name)
    except Exception as exp:
        message = str(exp)
        print(f'update_cfn_stack :: {message}')
        check_if_create_in_progress(exp, stack_name, current_branch, cfn_code=cfn_code, cfn_location=cfn_location, parameters=parameters, origin='update')

def create_cfn_stack(stack_name, current_branch, cfn_code=None, cfn_location=None, parameters=[]):
    print(f'Creating {stack_name} stack')
    cfn_client = get_cfn_client()
    try:
        if cfn_code:
            cfn_client.create_stack(
                StackName=stack_name,
                TemplateBody=cfn_code,
                Parameters=parameters,
                Capabilities=['CAPABILITY_IAM','CAPABILITY_AUTO_EXPAND'],
                Tags=[{'Key':'branch', 'Value': current_branch.replace('-','')}]
            )
        elif cfn_location:
            print(cfn_location)
            cfn_client.create_stack(
                StackName=stack_name,
                TemplateURL=cfn_location,
                Parameters=parameters,
                Capabilities=['CAPABILITY_IAM','CAPABILITY_AUTO_EXPAND'],
                Tags=[{'Key':'branch', 'Value': current_branch.replace('-','')}]
            )
        else:
            raise Exception('Must try cfn stream or s3 location')
        waiter = cfn_client.get_waiter('stack_create_complete')
        waiter.wait(StackName=stack_name)
    except cfn_client.exceptions.AlreadyExistsException as exp:
        message = str(exp)
        print(f'create_cfn_stack :: {message}')
        update_cfn_stack(stack_name, current_branch, cfn_code=cfn_code, cfn_location=cfn_location, parameters=parameters)
    except Exception as exp:
        check_if_create_in_progress(exp, stack_name, current_branch, cfn_code=cfn_code, cfn_location=cfn_location, parameters=parameters, origin='create')

def check_if_create_in_progress(exp, stack_name, current_branch, cfn_code=None, cfn_location=None, parameters=[], origin=None):
    exp_message = str(exp)
    if 'CREATE_IN_PROGRESS' in exp_message or 'UPDATE_IN_PROGRESS' in exp_message:
        print(f'Found create in progress stack {stack_name}')
        if not origin:
            origin = 'create'
        cfn_client = get_cfn_client()
        print('Waiting till previous deployment finishes')
        waiter = cfn_client.get_waiter('stack_update_complete')
        waiter.wait(StackName=stack_name)
        print(f'Preparing the action {origin}')
        if origin == 'create':
            create_cfn_stack(stack_name, current_branch, cfn_code=cfn_code, cfn_location=cfn_location, parameters=parameters)
        elif origin == 'update':
            update_cfn_stack(stack_name, current_branch, cfn_code=cfn_code, cfn_location=cfn_location, parameters=parameters)
        else:
            raise Exception('Invalid origin')
    elif 'No updates are to be performed' in exp_message:
        print(exp_message)
    else:
        raise exp

def md5(fname):
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def get_api_gw_resources(api_id, items_list=[], position=None):
    api_client = get_apigw_client()
    resources_output = None
    if position:
        resources_output = api_client.get_resources(
            restApiId=api_id,
            position=position
        )
    else:
        resources_output = api_client.get_resources(
            restApiId=api_id
        )
    items = resources_output.get('items', []) + items_list
    if resources_output.get('position'):
        return get_api_gw_resources(api_id, items_list=items, position=resources_output.get('position'))
    return items

def apply_cors(api_id, resource_id, method_type):
    cors_command_base = f'aws apigateway put-integration-response --rest-api-id {api_id} --resource-id {resource_id} --http-method {method_type} --status-code 200 --selection-pattern 200 --response-parameters'
    response_params = '\'{\"method.response.header.Access-Control-Allow-Origin\": \"\'\"\'\"\'*\'\"\'\"\'\"}\''
    os.system(f'{cors_command_base} {response_params}')


def get_branch_alias(branch_name):
    return 'dev' if branch_name == 'master' else branch_name.replace('-','')