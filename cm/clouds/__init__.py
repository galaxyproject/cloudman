class CloudInterface(object):
    # Global fields
    ami = None
    instance_type = None
    instance_id = None
    zone = None
    security_groups = None
    key_pair_name = None
    ec2_conn = None
    s3_conn = None
    self_private_ip = None
    self_public_ip = None
    instance_type = None
    fqdn = None