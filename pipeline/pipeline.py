import boto3
import os
from datetime import datetime
from random import randint
import sys
import json
import yaml
import uuid

def main():
    """ Control function for the pipeline """
    args = sys.argv    
    current_branch = pipeline_util.get_current_git_branch()
    print(f'branch :: {current_branch}')
    code_s3_bucket_name = pipeline_util.get_code_bucket(current_branch)
    print(f's3 bucket name :: {code_s3_bucket_name}')
    main_stack_name = pipeline_util.get_main_stack_name(current_branch)
    print(f'stack  name :: {main_stack_name}')
    operation = decode_operation(args)
    if 'UNITTESTS' == operation:
        test_code()
    if 'DEPLOY' == operation:
        create_util_stack(main_stack_name, code_s3_bucket_name, current_branch)
        artifact_checksum = package_code()
        copy_infra_code_to_bucket(code_s3_bucket_name) 
        copy_code_to_bucket(code_s3_bucket_name, artifact_checksum)
        code_artifact = f'code/package-{artifact_checksum}.zip'
        deploy(main_stack_name, code_s3_bucket_name, current_branch, code_artifact) 



def test_code():
    os.system('pipenv run pip freeze > requirements.txt')
    os.system('pip install -t . -r requirements.txt')
    os.system('pylint handlers gtmedia tests')
    os.system('pytest -s tests') 

def package_code():
    os.system('python -m zipfile -c package/package.zip package/tempcode/*')
    checksum = pipeline_util.md5('package/package.zip')
    return checksum

def decode_operation(args):
    if len(args) >=2  and args[1] == '-s' and args[2] == 'deploy':
        return 'DEPLOY'
    elif len(args) >=2  and args[1] == '-s' and args[2] == 'unittests':
        return 'UNITTESTS'
    elif len(args) >=2  and args[1] == '-s' and args[2] == 'teardown':
        return 'TEARDOWN'
    else:
        raise Exception(f'Invalid input :: {args}')


def copy_infra_code_to_bucket(bucket_name):
    os.system(f'aws s3 cp --recursive pipeline/code s3://{bucket_name}/infracode/')

def copy_code_to_bucket(bucket_name, checksum):
    os.system(f'aws s3 cp package/package.zip s3://{bucket_name}/code/package-{checksum}.zip')

def deploy(stack_name, bucket_name, current_branch, code_artifact):
    parameters = parameters_for_main_stack(bucket_name, code_artifact, stack_name, current_branch)    
    cfn_location = f'https://s3.amazonaws.com/{bucket_name}/infracode/stack.yml'
    pipeline_util.create_cfn_stack(f'{stack_name}', current_branch, cfn_code=None,cfn_location=cfn_location,parameters=parameters)


def parameters_for_main_stack(bucket_name, code_artifact, stack_name, current_branch):
    parameters = [] 
    parameters.append(
        {
            'ParameterKey':'S3BucketLocation',
            'ParameterValue': bucket_name
        }
    )
    parameters.append(
        {
            'ParameterKey':'CodeArtifactName',
            'ParameterValue': code_artifact
        }
    )
    parameters.append(
        {
            'ParameterKey':'FormattedCurrentBranch',
            'ParameterValue': current_branch.replace('-','')
        }
    )
    parameters.append(
        {
            'ParameterKey':'BranchAlias',
            'ParameterValue': pipeline_util.get_branch_alias(current_branch)
        }
    )
    parameters.append(
        {
            'ParameterKey':'StageName',
            'ParameterValue': get_stage_name(current_branch)
        }
    )
    parameters.append(
        {
            'ParameterKey':'ImageBucketOrigin',
            'ParameterValue': get_image_bucket(current_branch)
        }
    )
    parameters.append(
        {
            'ParameterKey':'AlternateDomain',
            'ParameterValue': get_alternate_domain(current_branch)
        }
    )
    parameters.append(
        {
            'ParameterKey':'AlternateDomainCertificateArn',
            'ParameterValue': get_certificate_arn(current_branch)
        }
    )
    parameters.append(
        {
            'ParameterKey':'BucketOriginAccessIdentity',
            'ParameterValue': get_bucket_origin_access_identity(current_branch)
        }
    )
    return parameters

def get_bucket_origin_access_identity(current_branch):    
    identity = None
    if current_branch == 'prod':
        identity = 'origin-access-identity/cloudfront/XXXXXXXXX'
    else:
        identity = 'origin-access-identity/cloudfront/YYYYYYYYY'
    return identity

def get_certificate_arn(current_branch):    
    arn = None
    if current_branch == 'prod':
        arn = 'arn:aws:acm:us-east-1:XXXXXXXXXXX:certificate/xxxxxxxxxxxxxxxxxxxxx'
    else:
        arn = 'arn:aws:acm:us-east-1:YYYYYYYYYYY:certificate/yyyyyyyyyyyyyyyyyyyyy'
    return arn

def get_alternate_domain(current_branch):    
    domain = None
    if current_branch == 'prod':
        domain = '<prod_domain_name_goes_here>'
    else:
        domain = '<dev_domain_name_goes_here>'
    return domain

def get_image_bucket(current_branch):    
    bucket = None
    if current_branch == 'prod':
        bucket = '<prod_image_bucket_origin>'
    else:
        bucket = '<dev_image_bucket_origin>'
    return bucket


def get_stage_name(current_branch):
    current_api_version = 'v1'
    stage_name = None
    if current_branch == 'main' or current_branch == 'master' or current_branch == 'staging' or current_branch == 'prod' or current_branch == 'dev':
        stage_name = current_api_version
    else:
        stage_name = f'{current_api_version}-{current_branch}'
    return stage_name

def create_util_stack(main_stack_name, bucket_name, current_branch):
    cfn_code = open('pipeline/util_code/code_util_stack.yml', 'r').read()
    stack_name = get_util_stack_name(main_stack_name)
    parameters = []
    parameters.append(
        {
            'ParameterKey':'CodeBucketName',
            'ParameterValue': bucket_name
        }
    )
    parameters.append(
        {
            'ParameterKey':'APICodeBucketName',
            'ParameterValue': f'{bucket_name}-api'
        }
    )
    parameters.append(
        {
            'ParameterKey':'CurrentBranch',
            'ParameterValue': current_branch.replace('-','')  
        }
    )
    pipeline_util.create_cfn_stack(stack_name, current_branch.replace('-',''), cfn_code=cfn_code, parameters=parameters)

def get_util_stack_name(main_stack_name):
    return f'util-stack-{main_stack_name}'

def generate_random():
    return randint(10000, 99999)


def find_cfn_parameters(cfn_code):
    resource_index = cfn_code.index('Resources:')
    cfn_code = cfn_code[:resource_index]
    cfn_json = yaml.load(cfn_code, Loader=yaml.SafeLoader)
    return cfn_json.get('Parameters')


def get_cfn_client():
    return boto3.client('cloudformation')


if __name__ == '__main__':
    import pipeline_util
    main()