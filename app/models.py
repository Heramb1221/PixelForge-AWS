import os
import uuid
import boto3
from datetime import datetime, timezone, timedelta
from flask import current_app
from boto3.dynamodb.conditions import Key, Attr

def get_table():
    dynamodb = boto3.resource('dynamodb', region_name=current_app.config['AWS_REGION'])
    return dynamodb.Table(current_app.config['DYNAMODB_TABLE_NAME'])

# Helper to normalize DynamoDB items into the dicts expected by the app
def _normalize(item):
    if not item:
        return None
    # Copy to avoid mutating the original
    res = dict(item)
    
    # Map common ID fields back
    if 'SK' in res:
        parts = res['SK'].split('#')
        if len(parts) > 1:
            res['id'] = parts[1]

    # Special handling for User ID (which is in PK)
    if res.get('PK', '').startswith('USER#') and res.get('SK') == 'METADATA':
        res['id'] = res['PK'].split('#')[1]
        
    # Map uppercase/camelCase attributes to snake_case
    mappings = {
        'Email': 'email',
        'PasswordHash': 'password_hash',
        'ProjectId': 'project_id',
        'Name': 'name',
        'Description': 'description',
        'Label': 'label',
        'Width': 'width',
        'Height': 'height',
        'Format': 'output_format',
        'SmartCrop': 'smart_crop',
        'OriginalKey': 'original_key',
        'OriginalFilename': 'original_filename',
        'ContentType': 'content_type',
        'SizeBytes': 'size_bytes',
        'Status': 'status',
        'ErrorMessage': 'error_message',
        'ProcessedAt': 'processed_at',
        'VariantProfileId': 'variant_profile_id',
        'ProcessedKey': 'processed_key',
        'BytesSaved': 'bytes_saved',
        'CreatedAt': 'created_at',
    }
    for dyn_k, app_k in mappings.items():
        if dyn_k in res:
            res[app_k] = res[dyn_k]
            
    return res

# ---------------------------------------------------------------- users ---
def create_user(email, password_hash):
    table = get_table()
    email_lower = email.lower()
    item = {
        'PK': f"USER#{email_lower}",
        'SK': 'METADATA',
        'Email': email_lower,
        'PasswordHash': password_hash,
        'CreatedAt': datetime.now(timezone.utc).isoformat()
    }
    table.put_item(Item=item)
    return _normalize(item)

def get_user_by_email(email):
    table = get_table()
    resp = table.get_item(Key={'PK': f"USER#{email.lower()}", 'SK': 'METADATA'})
    return _normalize(resp.get('Item'))

def any_user_exists():
    table = get_table()
    # Query the GSI for anything with SK = METADATA and PK starts with USER#
    # But since we just want to know if *any* user exists, a scan with limit is fine
    resp = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Key('PK').begins_with('USER#'),
        Limit=1
    )
    return len(resp.get('Items', [])) > 0

# ------------------------------------------------------------- projects ---
def create_project(user_id, name, description):
    table = get_table()
    project_id = str(uuid.uuid4())
    item = {
        'PK': f"USER#{user_id}",
        'SK': f"PROJ#{project_id}",
        'ProjectId': project_id,
        'Name': name,
        'Description': description,
        'TotalUploads': 0,
        'FailedUploads': 0,
        'BytesSaved': 0,
        'CreatedAt': datetime.now(timezone.utc).isoformat()
    }
    table.put_item(Item=item)
    return _normalize(item)

def list_projects(user_id):
    table = get_table()
    resp = table.query(
        KeyConditionExpression=Key('PK').eq(f"USER#{user_id}") & Key('SK').begins_with('PROJ#')
    )
    return [_normalize(item) for item in resp.get('Items', [])]

def get_project(project_id, user_id=None):
    table = get_table()
    if user_id:
        resp = table.get_item(Key={'PK': f"USER#{user_id}", 'SK': f"PROJ#{project_id}"})
        return _normalize(resp.get('Item'))
    else:
        resp = table.query(
            IndexName='SK-index',
            KeyConditionExpression=Key('SK').eq(f"PROJ#{project_id}")
        )
        items = resp.get('Items', [])
        return _normalize(items[0]) if items else None

def delete_project(project_id, user_id):
    table = get_table()
    # In DynamoDB, to delete a project completely we must also delete all profiles and images inside it.
    # For this capstone, we will delete the Project item, the Profiles, and Images.
    # A real system might use TTL or a batch job.
    
    # 1. Delete the Project item
    table.delete_item(Key={'PK': f"USER#{user_id}", 'SK': f"PROJ#{project_id}"})
    
    # 2. Delete all Profiles and Images (PK = PROJ#project_id)
    resp = table.query(KeyConditionExpression=Key('PK').eq(f"PROJ#{project_id}"))
    with table.batch_writer() as batch:
        for item in resp.get('Items', []):
            batch.delete_item(Key={'PK': item['PK'], 'SK': item['SK']})

def get_project_analytics(project_id):
    project = get_project(project_id)
    if not project:
        return None
        
    images = list_images(project_id)
    total_images = len(images)
    completed_images = sum(1 for img in images if img.get('status') == 'done')
    failed_images = sum(1 for img in images if img.get('status') == 'failed')
    total_original_bytes = sum(int(img.get('size_bytes', 0) or 0) for img in images)
    
    total_variants_generated = 0
    total_variant_bytes = 0
    total_bytes_saved = 0
    
    for img in images:
        if img.get('status') == 'done':
            variants = list_image_variants(img['id'])
            total_variants_generated += len(variants)
            total_variant_bytes += sum(int(v.get('size_bytes', 0) or 0) for v in variants)
            total_bytes_saved += sum(int(v.get('bytes_saved', 0) or 0) for v in variants)

    return {
        'total_images': total_images,
        'completed_images': completed_images,
        'failed_images': failed_images,
        'total_variants_generated': total_variants_generated,
        'total_original_bytes': total_original_bytes,
        'total_variant_bytes': total_variant_bytes,
        'total_bytes_saved': total_bytes_saved
    }

def record_event(project_id, event_type, bytes_saved=0):
    table = get_table()
    # Find the user_id (PK) for this project
    project = get_project(project_id)
    if not project: return
    
    pk = project.get('PK')
    if not pk:
        # If it was normalized away, we can query it again or reconstruct it if we had user_id
        resp = table.query(IndexName='SK-index', KeyConditionExpression=Key('SK').eq(f"PROJ#{project_id}"))
        if not resp.get('Items'): return
        pk = resp['Items'][0]['PK']

    update_expr = []
    expr_attr_vals = {}
    
    if event_type == 'upload_completed':
        update_expr.append("TotalUploads = TotalUploads + :one")
        update_expr.append("BytesSaved = BytesSaved + :bs")
        expr_attr_vals[':one'] = 1
        expr_attr_vals[':bs'] = bytes_saved
    elif event_type == 'processing_failed':
        update_expr.append("TotalUploads = TotalUploads + :one")
        update_expr.append("FailedUploads = FailedUploads + :one")
        expr_attr_vals[':one'] = 1
    elif event_type == 'cleanup_deleted':
        # Don't let it go below 0
        update_expr.append("TotalUploads = TotalUploads - :one")
        expr_attr_vals[':one'] = 1
        
    if update_expr:
        try:
            table.update_item(
                Key={'PK': pk, 'SK': f"PROJ#{project_id}"},
                UpdateExpression="SET " + ", ".join(update_expr),
                ExpressionAttributeValues=expr_attr_vals
            )
        except Exception:
            pass # Ignore underflows or missing fields if we didn't init them

# ------------------------------------------------------- variant profiles -
def create_variant_profile(project_id, label, width, height, output_format, smart_crop):
    table = get_table()
    profile_id = str(uuid.uuid4())
    item = {
        'PK': f"PROJ#{project_id}",
        'SK': f"VAR#{profile_id}",
        'ProjectId': project_id,
        'Label': label,
        'Width': width,
        'Height': height,
        'Format': output_format,
        'SmartCrop': smart_crop
    }
    table.put_item(Item=item)
    return _normalize(item)

def list_variant_profiles(project_id):
    table = get_table()
    resp = table.query(
        KeyConditionExpression=Key('PK').eq(f"PROJ#{project_id}") & Key('SK').begins_with('VAR#')
    )
    return [_normalize(item) for item in resp.get('Items', [])]

def delete_variant_profile(profile_id, project_id):
    table = get_table()
    table.delete_item(Key={'PK': f"PROJ#{project_id}", 'SK': f"VAR#{profile_id}"})

# ------------------------------------------------------------------ images
def create_image(project_id, original_key, original_filename, content_type, size_bytes):
    table = get_table()
    image_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    item = {
        'PK': f"PROJ#{project_id}",
        'SK': f"IMG#{image_id}",
        'ProjectId': project_id,
        'OriginalKey': original_key,
        'OriginalFilename': original_filename,
        'ContentType': content_type,
        'SizeBytes': size_bytes,
        'Status': 'pending',
        'CreatedAt': now
    }
    table.put_item(Item=item)
    return _normalize(item)

def get_image(image_id):
    table = get_table()
    resp = table.query(
        IndexName='SK-index',
        KeyConditionExpression=Key('SK').eq(f"IMG#{image_id}")
    )
    items = resp.get('Items', [])
    return _normalize(items[0]) if items else None

def get_image_by_key(original_key):
    table = get_table()
    resp = table.query(
        IndexName='OriginalKey-index',
        KeyConditionExpression=Key('OriginalKey').eq(original_key)
    )
    items = resp.get('Items', [])
    return _normalize(items[0]) if items else None

def update_image_status(image_id, status, error_message=None, processed_at=None):
    table = get_table()
    # Find the PK (project_id)
    img = get_image(image_id)
    if not img: return
    
    update_expr = "SET #st = :status"
    expr_attr_names = {'#st': 'Status'}
    expr_attr_vals = {':status': status}
    
    if error_message:
        update_expr += ", ErrorMessage = :err"
        expr_attr_vals[':err'] = error_message
        
    if processed_at:
        update_expr += ", ProcessedAt = :pat"
        expr_attr_vals[':pat'] = processed_at.isoformat() if isinstance(processed_at, datetime) else processed_at
        
    table.update_item(
        Key={'PK': f"PROJ#{img['project_id']}", 'SK': f"IMG#{image_id}"},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=expr_attr_names,
        ExpressionAttributeValues=expr_attr_vals
    )

def delete_image(image_id):
    table = get_table()
    img = get_image(image_id)
    if not img: return
    
    # 1. Delete image
    table.delete_item(Key={'PK': f"PROJ#{img['project_id']}", 'SK': f"IMG#{image_id}"})
    
    # 2. Delete all its variants
    resp = table.query(KeyConditionExpression=Key('PK').eq(f"IMG#{image_id}"))
    with table.batch_writer() as batch:
        for item in resp.get('Items', []):
            batch.delete_item(Key={'PK': item['PK'], 'SK': item['SK']})

def list_images(project_id):
    table = get_table()
    resp = table.query(
        KeyConditionExpression=Key('PK').eq(f"PROJ#{project_id}") & Key('SK').begins_with('IMG#')
    )
    return [_normalize(item) for item in resp.get('Items', [])]

def list_stale_images_with_variants(max_age_hours):
    table = get_table()
    # DynamoDB doesn't have an easy way to list all stale images globally without a GSI or Scan.
    # Since this is a capstone cleanup job, we'll scan for all IMGs older than max_age_hours.
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
    
    resp = table.scan(
        FilterExpression=Key('SK').begins_with('IMG#') & Attr('CreatedAt').lt(cutoff)
    )
    return [_normalize(item) for item in resp.get('Items', [])]

# ---------------------------------------------------------------- variants
def create_image_variant(image_id, variant_profile_id, processed_key, width, height, size_bytes, bytes_saved):
    table = get_table()
    variant_id = str(uuid.uuid4())
    img = get_image(image_id)
    if not img: return None
    
    profile_item = table.get_item(Key={'PK': f"PROJ#{img['project_id']}", 'SK': f"VAR#{variant_profile_id}"}).get('Item')
    label = profile_item['Label'] if profile_item else 'unknown'
    output_format = profile_item['Format'] if profile_item else 'unknown'
    
    item = {
        'PK': f"IMG#{image_id}",
        'SK': f"VAR#{variant_id}",
        'VariantProfileId': variant_profile_id,
        'ProcessedKey': processed_key,
        'Width': width,
        'Height': height,
        'SizeBytes': size_bytes,
        'BytesSaved': bytes_saved,
        'Label': label,
        'Format': output_format
    }
    table.put_item(Item=item)
    return _normalize(item)

def list_image_variants(image_id):
    table = get_table()
    resp = table.query(
        KeyConditionExpression=Key('PK').eq(f"IMG#{image_id}") & Key('SK').begins_with('VAR#')
    )
    return [_normalize(item) for item in resp.get('Items', [])]