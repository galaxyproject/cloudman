from boto.s3.key import Key
from boto.exception import S3ResponseError


def _get_file_from_bucket(log, s3_conn, bucket_name, remote_filename, local_filename):
    log.debug("Getting file %s from bucket %s" % (remote_filename, bucket_name))
    try:
        b = s3_conn.get_bucket(bucket_name, validate=False)
        k = Key(b, remote_filename)

        log.debug("Attempting to retrieve file '%s' from bucket '%s'" % (
            remote_filename, bucket_name))
        if k.exists():
            k.get_contents_to_filename(local_filename)
            log.info("Successfully retrieved file '%s' from bucket '%s' via connection '%s' to '%s'"
                % (remote_filename, bucket_name, s3_conn.host, local_filename))
            return True
        else:
            log.error("File '%s' in bucket '%s' not found." % (
                remote_filename, bucket_name))
            return False
    except S3ResponseError, e:
        log.error("Failed to get file '%s' from bucket '%s': %s" %
                  (remote_filename, bucket_name, e))
        return False


def _key_exists_in_bucket(log, s3_conn, bucket_name, key_name):
    """
    Check if an object (ie, key) of name ``key_name`` exists in bucket
    ``bucket_name``. Return ``True`` if so, ``False`` otherwise.
    """
    b = s3_conn.get_bucket(bucket_name, validate=False)
    k = Key(b, key_name)
    log.debug("Checking if key '%s' exists in bucket '%s'" % (
        key_name, bucket_name))
    return k.exists()
