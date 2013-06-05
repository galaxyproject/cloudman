from boto.s3.key import Key
from boto.exception import S3ResponseError


def _get_file_from_bucket(log, s3_conn, bucket_name, remote_filename, local_filename):
    try:
        b = s3_conn.get_bucket(bucket_name)
        k = Key(b, remote_filename)

        log.debug("Attempting to retrieve file '%s' from bucket '%s'" % (
            remote_filename, bucket_name))
        if k.exists():
            k.get_contents_to_filename(local_filename)
            log.info("Successfully retrieved file '%s' from bucket '%s' to '%s'" % (
                remote_filename, bucket_name, local_filename))
            return True
        else:
            log.error("File '%s' in bucket '%s' not found." % (
                remote_filename, bucket_name))
            return False
    except S3ResponseError, e:
        log.error("Failed to get file '%s' from bucket '%s': %s" %
                  (remote_filename, bucket_name, e))
        return False
