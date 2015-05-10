#!/usr/bin/python
"""A number of utility functions useful throughout the framework."""
import commands
import contextlib
import datetime as dt
import errno
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import yaml
import string
import random
import grp
import pwd
import requests

from boto.exception import S3CreateError, S3ResponseError
from boto.s3.acl import ACL
from boto.s3.key import Key
from tempfile import mkstemp, NamedTemporaryFile

from cm.services import ServiceRole

log = logging.getLogger('cloudman')


def load_yaml_file(filename):
    """Load ``filename`` in YAML format and return it as a dict"""
    with open(filename) as ud_file:
        ud = yaml.load(ud_file)
    return ud


def dump_yaml_to_file(data, filename):
    """Dump (i.e., store) ``data`` dict into a YAML file ``filename``"""
    with open(filename, 'w') as f:
        yaml.dump(data, f, default_flow_style=False)


def merge_yaml_objects(user, default):
    """
    Merge fields from user data ``user`` YAML object and default data ``default``
    YAML object.

    If there are conflicts, value from the user data object are kept.
    """
    if isinstance(user, dict) and isinstance(default, dict):
        for k, v in default.iteritems():
            if k not in user:
                user[k] = v
            else:
                user[k] = merge_yaml_objects(user[k], v)
    return user


def normalize_user_data(app, ud):
    """
    Normalize user data format to a consistent representation used within CloudMan.

    This is useful as user data and also persistent data evolve over time and thus
    calling this method at app start enables any necessary translation to happen.
    """
    if ud.get('persistent_data_version', 1) < app.PERSISTENT_DATA_VERSION:
        # First make a backup of the deprecated persistent data file
        s3_conn = app.cloud_interface.get_s3_connection()
        copy_file_in_bucket(
            s3_conn, ud['bucket_cluster'], ud['bucket_cluster'],
            'persistent_data.yaml', 'persistent_data-deprecated.yaml', preserve_acl=False,
            validate=False)
        # Convert (i.e., normalize) v2 ud
        if 'filesystems' in ud:
            log.debug("Normalizing v2 user data")
            for fs in ud['filesystems']:
                if 'roles' not in fs:
                    fs['roles'] = ServiceRole.legacy_convert(fs['name'])
                if 'delete_on_termination' not in fs:
                    if fs['kind'] == 'snapshot':
                        fs['delete_on_termination'] = True
                    else:
                        fs['delete_on_termination'] = False
            for svc in ud.get('services', []):
                if 'roles' not in svc:
                    svc['roles'] = ServiceRole.legacy_convert(
                        svc.get('name', 'NoName'))
        # Convert (i.e., normalize) v1 ud
        if "static_filesystems" in ud or "data_filesystems" in ud:
            log.debug("Normalizing v1 user data")
            if 'filesystems' not in ud:
                ud['filesystems'] = []
            if 'static_filesystems' in ud:
                for vol in ud['static_filesystems']:
                    # Create a mapping between the old and the new format styles
                    # Some assumptions are made here; namely, all static file systems
                    # in the original data are assumed delete_on_termination, their name
                    # defines their role and they are mounted under /mnt/<name>
                    roles = ServiceRole.legacy_convert(vol['filesystem'])
                    fs = {'kind': 'snapshot', 'name': vol['filesystem'],
                          'roles': roles, 'delete_on_termination': True,
                          'mount_point': os.path.join('/mnt', vol['filesystem']),
                          'ids': [vol['snap_id']]}
                    ud['filesystems'].append(fs)
                ud.pop('static_filesystems')
                ud['cluster_type'] = 'Galaxy'
            if 'data_filesystems' in ud:
                for fs_name, fs in ud['data_filesystems'].items():
                    fs = {'kind': 'volume', 'name': fs_name,
                          'roles': ServiceRole.legacy_convert(fs_name), 'delete_on_termination': False,
                          'mount_point': os.path.join('/mnt', fs_name),
                          'ids': [fs[0]['vol_id']]}
                    ud['filesystems'].append(fs)
                ud.pop('data_filesystems')
                if 'cluster_type' not in ud:
                    ud['cluster_type'] = 'Data'
            if 'galaxy_home' in ud:
                ud.pop('galaxy_home')
        if 'services' in ud and 'service' in ud['services'][0]:
            log.debug("Normalizing v1 service user data")
            old_svc_list = ud['services']
            ud['services'] = []
            # clear 'services' and replace with the new format
            for svc in old_svc_list:
                if 'roles' not in svc:
                    normalized_svc = {'name': svc['service'], 'roles':
                                      ServiceRole.legacy_convert(svc['service'])}
                    ud['services'].append(normalized_svc)
    return ud


@contextlib.contextmanager
def flock(path, wait_delay=1):
    """
    A lockfile implementation (from http://code.activestate.com/recipes/576572/)
    It is primarily intended to be used as a semaphore with multithreaded code.

    Use like so:
    with flock('.lockfile'):
       # do whatever.
    """
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
            time.sleep(wait_delay)
            continue
        else:
            break
    try:
        yield fd
    finally:
        os.close(fd)
        os.unlink(path)


def format_seconds(delta):
    """
    Given a time delta object, calculate the total number of seconds and return
    it as a string.
    """
    def _total_seconds(td):
        return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10 ** 6) / 10 ** 6
    return '%s' % (_total_seconds(delta))


def format_time_delta(delta):
    """
    Given a time delta object, convert it into a nice, human readable string.
    For example, given 290 seconds, return 4m 50s.
    """
    d = delta.days
    h = delta.seconds / 3600
    m = (delta.seconds % 3600) / 60
    s = delta.seconds % 60

    if d > 0:
        return '%sd %sh' % (d, h)
    elif h > 0:
        return '%sh %sm' % (h, m)
    else:
        return '%sm %ss' % (m, s)


def bucket_exists(s3_conn, bucket_name):
    """Check if bucket `bucket_name` exists."""
    if s3_conn is None:
        log.debug("Checking if S3 bucket exists, but no S3 connection provided!?")
        return False
    if bucket_name:
        try:
            b = s3_conn.get_bucket(bucket_name, validate=False)
            try:
                b.get_all_keys(maxkeys=0)
            except S3ResponseError:
                b = None  # The bucket does not exist
            if b:
                # log.debug("Checking if bucket '%s' exists... it does." %
                # bucket_name)
                return True
            else:
                log.debug("Checking if bucket '%s' exists... it does not." % bucket_name)
                return False
        except S3ResponseError as e:
            log.error("Failed to lookup bucket '%s': %s" % (bucket_name, e))
    else:
        log.error("Cannot lookup bucket with no name.")
        return False


def create_bucket(s3_conn, bucket_name):
    """Create a bucket called `bucket_name`."""
    try:
        log.debug("Creating bucket '%s'." % bucket_name)
        s3_conn.create_bucket(bucket_name)
        log.debug("Created bucket '%s'." % bucket_name)
    except (S3ResponseError, S3CreateError) as e:
        log.error("Failed to create bucket '%s': %s" % (bucket_name, e))
        return False
    return True


def get_bucket(s3_conn, bucket_name, validate=False):
    """
    Get handle to bucket `bucket_name`, optionally validating that the bucket
    actually exists by issuing a HEAD request.
    """
    b = None
    if bucket_exists(s3_conn, bucket_name):
        for i in range(0, 5):
            try:
                b = s3_conn.get_bucket(bucket_name, validate=validate)
                break
            except S3ResponseError:
                log.error("Problem connecting to bucket '%s', attempt %s/5" % (
                    bucket_name, i + 1))
                time.sleep(2)
    else:
        log.debug("Attempted to get bucket %s but it doesn't exist." % bucket_name)
    return b


def make_bucket_public(s3_conn, bucket_name, recursive=False):
    """
    Make bucket `bucket_name` public, meaning anyone can read its contents. If
    `recursive` is set, do so for all objects contained in the bucket.
    """
    b = get_bucket(s3_conn, bucket_name)
    if b:
        try:
            b.make_public(recursive=recursive)
            log.debug("Bucket '%s' made public" % bucket_name)
            return True
        except S3ResponseError as e:
            log.error(
                "Could not make bucket '%s' public: %s" % (bucket_name, e))
    return False


def make_key_public(s3_conn, bucket_name, key_name):
    """
    Set the ACL setting for `key_name` in `bucket_name` so anyone can read the
    contents of the key.
    """
    b = get_bucket(s3_conn, bucket_name)
    if b:
        try:
            k = Key(b, key_name)
            if k.exists():
                k.make_public()
                log.debug("Key '%s' made public" % key_name)
                return True
        except S3ResponseError as e:
            log.error("Could not make key '%s' public: %s" % (key_name, e))
    return False


def add_bucket_user_grant(s3_conn, bucket_name, permission, canonical_ids, recursive=False):
    """
    Boto wrapper that provides a quick way to add a canonical
    user grant to a bucket.

    :type permission: string
    :param permission: The permission being granted. Should be one of:
                       (READ, WRITE, READ_ACP, WRITE_ACP, FULL_CONTROL).

    :type user_id: list of strings
    :param canonical_ids: A list of strings with canonical user ids associated
                        with the AWS account your are granting the permission to.

    :type recursive: boolean
    :param recursive: A boolean value to controls whether the command
                      will apply the grant to all keys within the bucket
                      or not.
    """
    b = get_bucket(s3_conn, bucket_name)
    if b:
        try:
            for c_id in canonical_ids:
                log.debug("Adding '%s' permission for bucket '%s' for users '%s'" %
                          (permission, bucket_name, c_id))
                b.add_user_grant(permission, c_id, recursive)
            return True
        except S3ResponseError as e:
            log.error("Could not add permission '%s' for bucket '%s': %s" % (
                permission, bucket_name, e))
    return False


def add_key_user_grant(s3_conn, bucket_name, key_name, permission, canonical_ids):
    """
    Boto wrapper that provides a quick way to add a canonical
    user grant to a key.

    :type permission: string
    :param permission: Name of the bucket where the key resides

    :type permission: string
    :param permission: Name of the key to add the permission to

    :type permission: string
    :param permission: The permission being granted. Should be one of:
                       (READ, WRITE, READ_ACP, WRITE_ACP, FULL_CONTROL).

    :type user_id: list of strings
    :param canonical_ids: A list of strings with canonical user ids associated
                        with the AWS account your are granting the permission to.
    """
    b = get_bucket(s3_conn, bucket_name)
    if b:
        try:
            k = Key(b, key_name)
            if k.exists():
                for c_id in canonical_ids:
                    log.debug("Adding '%s' permission for key '%s' for user '%s'" % (
                        permission, key_name, c_id))
                    k.add_user_grant(permission, c_id)
                return True
        except S3ResponseError as e:
            log.error("Could not add permission '%s' for bucket '%s': %s" % (
                permission, bucket_name, e))
    return False


def get_list_of_bucket_folder_users(s3_conn, bucket_name, folder_name, exclude_power_users=True):
    """
    Retrieve a list of users that are associated with a key in a folder (i.e., prefix)
    in the provided bucket and have READ grant. Note that this method assumes all
    of the keys in the given folder have the same ACL and the method thus looks
    only at the very first key in the folder. Also, any users

    :type s3_conn: boto.s3.connection.S3Connection
    :param s3_conn: Established boto connection to S3 that has access to bucket_name

    :type bucket_name: string
    :param bucket_name: Name of the bucket in which the given folder/prefix is
                        stored

    :type folder_name: string
    :param folder_name: Allows limit the listing of keys in the given bucket to a
                   particular prefix. This has the effect of iterating through
                   'folders' within a bucket. For example, if you call the method
                   with folder_name='/foo/' then the iterator will only cycle
                   through the keys that begin with the string '/foo/'.
                   A valid example would be 'shared/2011-03-31--19-43/'

    :type exclude_power_users: boolean
    :param exclude_power_users: If True, folder users with FULL_CONTROL grant
                   are not included in the folder user list
    """
    users = []  # Current list of users retrieved from folder's ACL
    key_list = None
    key_acl = None
    b = get_bucket(s3_conn, bucket_name)
    if b:
        try:
            key_list = b.get_all_keys(prefix=folder_name, delimiter='/')
            # for k in key_list:
            #     print k.name#, k.get_acl().acl.grants[0].type
            if len(key_list) > 0:
                key = key_list[0]
                # Just get one key assuming all keys will have the same ACL
                key_acl = key.get_acl()
            if key_acl:
                power_users = []
                for grant in key_acl.acl.grants:
                    # log.debug("folder_name: %s, %s, %s, %s, %s." %
                    # (folder_name, key.name, grant.type, grant.display_name,
                    # grant.permission))
                    if grant.permission == 'FULL_CONTROL':
                        power_users.append(grant.display_name)
                    if grant.type == 'Group' and 'Group' not in users:
                        # Group grants (i.e., public) are simply listed as
                        # Group under grant.type so catch that
                        users.append(u'Group')
                    elif grant.permission == 'READ' and grant.type != 'Group' and grant.display_name not in users:
                        users.append(grant.display_name)
                # Users w/ FULL_CONTROL are optionally not included in the
                # folder user list
                if exclude_power_users:
                    for pu in power_users:
                        if pu in users:
                            users.remove(pu)
        except S3ResponseError as e:
            log.error("Error getting list of folder '%s' users for bucket '%s': %s" % (
                folder_name, bucket_name, e))
    # log.debug("List of users for folder '%s' in bucket '%s': %s" %
    # (folder_name, bucket_name, users))
    return users


def get_users_with_grant_on_only_this_folder(s3_conn, bucket_name, folder_name):
    """
    This method is used when dealing with bucket permissions of shared instances.
    The method's intent is to isolate the set of users that have (READ) grant on
    a given folder and no other (shared) folder within the given bucket.
    Obtained results can then be used to set the permissions on the bucket root.

    See also: get_list_of_bucket_folder_users

    :type s3_conn: boto.s3.connection.S3Connection
    :param s3_conn: Established boto connection to S3 that has access to bucket_name

    :type bucket_name: string
    :param bucket_name: Name of the bucket in which the given folder is stored

    :type folder_name: string
    :param folder_name: Name of the (shared) folder whose grants will be examined
                        and compared to other (shared) folders in the same bucket.
                        A valid example would be 'shared/2011-03-31--19-43/'
    """
    users_with_grant = []
    # List of users with grant on given folder and no other (shared) folder in
    # bucket
    other_users = []  # List of users on other (shared) folders in given bucket
    folder_users = get_list_of_bucket_folder_users(
        s3_conn, bucket_name, folder_name)
    # log.debug("List of users on to-be-deleted shared folder '%s': %s" %
    # (folder_name, folder_users))
    b = get_bucket(s3_conn, bucket_name)
    if b:
        try:
            # Get list of shared folders in given bucket
            folder_list = b.get_all_keys(prefix='shared/', delimiter='/')
            # Inspect each shared folder's user grants and create a list of all users
            # with grants on those folders
            for f in folder_list:
                if f.name != folder_name:
                    fu = get_list_of_bucket_folder_users(
                        s3_conn, bucket_name, f.name)
                    for u in fu:
                        if u not in other_users:
                            other_users.append(u)
            # log.debug("List of users on other shared folders: %s" % other_users)
            # Find list of users in that have grants only on 'folder_name' and no
            # other shared folder in the given bucket
            for u in folder_users:
                if u not in other_users:
                    users_with_grant.append(u)
        except S3ResponseError as e:
            log.error("Error isolating list of folder '%s' users for bucket '%s': %s" % (
                folder_name, bucket_name, e))
    log.debug("List of users whose bucket grant is to be removed because shared folder '%s' is being deleted: %s"
              % (folder_name, users_with_grant))
    return users_with_grant


def adjust_bucket_acl(s3_conn, bucket_name, users_whose_grant_to_remove):
    """
    Adjust the ACL on given bucket and remove grants for all the mentioned users.

    :type s3_conn: boto.s3.connection.S3Connection
    :param s3_conn: Established boto connection to S3 that has access to bucket_name

    :type bucket_name: string
    :param bucket_name: Name of the bucket for which to adjust the ACL

    :type users_whose_grant_to_remove: list
    :param users_whose_grant_to_remove: List of user names (as defined in bucket's
                initial ACL, e.g., ['afgane', 'cloud']) whose grant is to be revoked.
    """
    bucket = get_bucket(s3_conn, bucket_name)
    if bucket:
        try:
            grants_to_keep = []
            # log.debug("All grants on bucket '%s' are following" % bucket_name)
            # Compose list of grants on the bucket that are to be kept, i.e., siphon
            # through the list of grants for bucket's users and the list of users
            # whose grant to remove and create a list of bucket grants to keep
            for g in bucket.get_acl().acl.grants:
                # log.debug("Grant -> permission: %s, user name: %s, grant type: %s" % (g.permission, g.display_name, g.type))
                # Public (i.e., group) permissions are kept under 'type' field
                # so check that first
                if g.type == 'Group' and 'Group' in users_whose_grant_to_remove:
                    pass
                elif g.display_name not in users_whose_grant_to_remove:
                    grants_to_keep.append(g)
            # Manipulate bucket's ACL now
            bucket_policy = bucket.get_acl(
            )  # Object for bucket's current policy (which holds the ACL)
            acl = ACL()  # Object for bucket's to-be ACL
            # Add all of the exiting (i.e., grants_to_keep) grants to the new
            # ACL object
            for gtk in grants_to_keep:
                acl.add_grant(gtk)
            # Update the policy and set bucket's ACL
            bucket_policy.acl = acl
            bucket.set_acl(bucket_policy)
            # log.debug("List of kept grants for bucket '%s'" % bucket_name)
            # for g in bucket_policy.acl.grants:
            # log.debug("Grant -> permission: %s, user name: %s, grant type:
            # %s" % (g.permission, g.display_name, g.type))
            log.debug("Removed grants on bucket '%s' for these users: %s" %
                      (bucket_name, users_whose_grant_to_remove))
            return True
        except S3ResponseError as e:
            log.error(
                "Error adjusting ACL for bucket '%s': %s" % (bucket_name, e))
    return False


def file_exists_in_bucket(s3_conn, bucket_name, remote_filename):
    """Check if remote_filename exists in bucket bucket_name.
    :rtype: bool
    :return: True if remote_filename exists in bucket_name
             False otherwise
    """
    b = get_bucket(s3_conn, bucket_name)
    if b:
        try:
            k = Key(b, remote_filename)
            if k.exists():
                return True
        except S3ResponseError:
            log.debug("Key '%s' in bucket '%s' does not exist." % (
                remote_filename, bucket_name))
    return False


def file_in_bucket_older_than_local(s3_conn, bucket_name, remote_filename, local_filename):
    """
    Check if the file in bucket has been modified before the local file.

    :rtype: bool
    :return: True of file in bucket is older than the local file or an error
             while checking the time occurs. False otherwise.
    """
    bucket = get_bucket(s3_conn, bucket_name)
    key = bucket.get_key(remote_filename)
    if key is not None:
        try:
            # Time format must be matched the time provided by boto field
            # .last_modified
            k_ts = dt.datetime.strptime(
                key.last_modified, "%a, %d %b %Y %H:%M:%S GMT")
        except Exception as e:
            log.debug("Could not get last modified timestamp for key '%s': %s" %
                      (remote_filename, e))
            return True
        try:
            return k_ts < dt.datetime.fromtimestamp(os.path.getmtime(local_filename))
        except Exception as e:
            log.debug("Trouble comparing local (%s) and remote (%s) file modified times: %s" % (
                local_filename, remote_filename, e))
            return True
    else:
        log.debug("Checking age of file in bucket (%s) against local file (%s) but file in bucket is None; updating file in bucket."
                  % (remote_filename, local_filename))
        return True


def get_file_from_bucket(conn, bucket_name, remote_filename, local_file, validate=False):
    """
    Retrieve a file `remote_filename` form bucket `bucket_name` to `local_file`.

    If `validate` is set, make sure the bucket exists by issuing a HEAD request
    before attempting to retrieve a file. Return `True` if the file was
    successfully retrieved. If an exception occurs or a zero size file is
    retrieved, return `False`.
    """
    if bucket_exists(conn, bucket_name):
        b = get_bucket(conn, bucket_name, validate)
        k = Key(b, remote_filename)
        try:
            k.get_contents_to_filename(local_file)
            if os.path.getsize(local_file) != 0:
                log.debug("Retrieved file '%s' from bucket '%s' on host '%s' to '%s'."
                          % (remote_filename, bucket_name, conn.host, local_file))
            else:
                log.warn("Got an empty file ({0})?!".format(local_file))
                return False
        except S3ResponseError as e:
            log.debug("Failed to get file '%s' from bucket '%s': %s" % (
                remote_filename, bucket_name, e))
            if os.path.exists(local_file):
                os.remove(local_file)  # Don't leave a partially downloaded or touched file
            return False
    else:
        log.debug("Bucket '%s' does not exist, did not get remote file '%s'" % (
            bucket_name, remote_filename))
        return False
    return True


def save_file_to_bucket(conn, bucket_name, remote_filename, local_file):
    b = get_bucket(conn, bucket_name)
    if b:
        k = Key(b, remote_filename)
        try:
            k.set_contents_from_filename(local_file)
            log.debug("Saved file '%s' of size %sB as '%s' to bucket '%s'"
                      % (local_file, k.size, remote_filename, bucket_name))
            # Store some metadata (key-value pairs) about the contents of the
            # file being uploaded
            k.set_metadata('date_uploaded', dt.datetime.utcnow())
        except S3ResponseError as e:
            log.error("Failed to save file local file '%s' to bucket '%s' as file '%s': %s" % (
                local_file, bucket_name, remote_filename, e))
            return False
        return True
    else:
        log.debug("Could not connect to bucket '%s'; remote file '%s' not saved to the bucket" % (
            bucket_name, remote_filename))
        return False


def copy_file_in_bucket(s3_conn, src_bucket_name, dest_bucket_name, orig_filename,
                        copy_filename, preserve_acl=True, validate=True):
    """
    Create a copy of an object `orig_filename` in `src_bucket_name` as
    `copy_filename` in `dest_bucket_name`, preserving the access control list
    settings by default. If `validate` is provided, the existence of source
    bucket will be validated before proceeding.
    Return `True` if the copy was successful; `False` otherwise.
    """
    b = get_bucket(s3_conn, src_bucket_name, validate)
    if b:
        try:
            log.debug(
                "Establishing handle with key object '%s'" % orig_filename)
            k = Key(b, orig_filename)
            log.debug(
                "Copying file '%s/%s' to file '%s/%s'" % (src_bucket_name,
                                                          orig_filename, dest_bucket_name, copy_filename))
            k.copy(dest_bucket_name, copy_filename, preserve_acl=preserve_acl)
            return True
        except S3ResponseError as e:
            log.debug("Error copying file '%s/%s' to file '%s/%s': %s" % (
                src_bucket_name, orig_filename, dest_bucket_name, copy_filename, e))
    return False


def delete_file_from_bucket(conn, bucket_name, remote_filename):
    """Delete an object from a bucket"""
    b = get_bucket(conn, bucket_name)
    if b:
        try:
            k = Key(b, remote_filename)
            log.debug("Deleting key object '%s' from bucket '%s'" % (
                remote_filename, bucket_name))
            k.delete()
            return True
        except S3ResponseError as e:
            log.error("Error deleting key '%s' from bucket '%s': %s" % (
                remote_filename, bucket_name, e))
    return False

def update_file_in_bucket(conn, bucket_name, local_filepath):
    """
    Updates file in bucket from its local counterpart.

    The script is saved only if the file does not already exist there
    and it is not older than the local one.
    """
    filename = os.path.basename(local_filepath)
    if not conn or not bucket_exists(conn, bucket_name):
        log.debug("No s3_conn or cluster bucket {0} does not exist; not "
                  "saving the pss in the bucket".format(bucket_name))
        return
    if file_in_bucket_older_than_local(conn,
                                       bucket_name,
                                       filename,
                                       local_filepath):
        if os.path.exists(local_filepath):
            log.debug("Saving current instance post start script (%s) to "
                      "cluster bucket '%s' as '%s'" %
                      (local_filepath, bucket_name,
                       filename))
            save_file_to_bucket(conn,
                                     bucket_name,
                                     filename, local_filepath)
        else:
            log.debug("No instance post start script (%s)" % local_filepath)
    else:
        log.debug("A current post start script {0} already exists in bucket "
                  "{1}; not updating it".format(filename,
                                                bucket_name))


def delete_bucket(conn, bucket_name):
    """
    Delete the bucket ``bucket_name``. This method will iterate through all the keys in
    the given bucket first and delete them. Finally, the bucket will be deleted.
    """
    try:
        b = get_bucket(conn, bucket_name)
        if b:
            keys = b.get_all_keys()
            for key in keys:
                key.delete()
            b.delete()
            log.info("Successfully deleted cluster bucket '%s'" % bucket_name)
    except S3ResponseError as e:
        log.error("Error deleting bucket '%s': %s" % (bucket_name, e))
    return True


def get_file_metadata(conn, bucket_name, remote_filename, metadata_key):
    """
    Get metadata value for the given key. If ``bucket_name`` or ``remote_filename``
    is not found, return ``None``.
    """
    log.debug("Getting metadata '%s' for file '%s' from bucket '%s'" %
              (metadata_key, remote_filename, bucket_name))
    b = get_bucket(conn, bucket_name)
    if b:
        k = b.get_key(remote_filename)
        if k and metadata_key:
            return k.get_metadata(metadata_key)
    return None


def set_file_metadata(conn, bucket_name, remote_filename, metadata_key, metadata_value):
    """
    Set metadata key-value pair for the remote file.

    :rtype: bool
    :return: If specified bucket and remote_filename exist, return True.
             Else, return False
    """
    log.debug("Setting metadata '%s' for file '%s' in bucket '%s'" % (
        metadata_key, remote_filename, bucket_name))

    b = get_bucket(conn, bucket_name)
    if b:
        k = b.get_key(remote_filename)
        if k and metadata_key:
            # Simply setting the metadata through set_metadata does not work.
            # Instead, must create in-place copy of the file with altered metadata:
            # http://groups.google.com/group/boto-
            # users/browse_thread/thread/9968d3fc4fc18842/29c680aad6e31b3e#29c680aad6e31b3e
            try:
                k.copy(bucket_name, remote_filename, metadata={
                       metadata_key: metadata_value}, preserve_acl=True)
                return True
            except S3ResponseError as e:
                log.debug("Could not set metadata for file '%s' in bucket '%s': %e" % (
                    remote_filename, bucket_name, e))
    return False


def get_file_from_public_location(config, remote_filename, local_file):
    """
    A fallback method which does the equivalent of a wget from
    the location specified in user data by (in order) default_bucket_url
    or bucket_default.
    """
    import urlparse

    url = config.get('default_bucket_url', None)
    bucket = config.get('bucket_default', None)

    if not url and bucket:
        s3_host = config.get('s3_host', 's3.amazonaws.com')
        s3_port = config.get('s3_port', 443)
        s3_conn_path = config.get('s3_conn_path', '/')

        s3_base_url = 'https://' + s3_host + ':' + str(s3_port) + '/'
        s3_base_url = urlparse.urljoin(s3_base_url, s3_conn_path)

        # TODO: assume openstack public bucket with specific access rights. Fix later
        if 'nectar' in config.get('cloud_name', '').lower():
            url = urlparse.urljoin(s3_base_url, '/V1/AUTH_377/')
        else:
            url = s3_base_url

        url = urlparse.urljoin(url, bucket + "/")

    elif not url and not bucket:
        log.error("Neither 'default_bucket_url' or 'bucket_default' in userdata")
        return False

    if not url.endswith('/'):
        url += '/'
    url = urlparse.urljoin(url, remote_filename)
    log.debug("Fetching file {0} and saving it as {1}".format(url, local_file))
    r = requests.get(url)
    if r.status_code == requests.codes.ok:
        f = open(local_file, 'w')
        f.write(r.content)
        f.close()
        return True
    else:
        log.warn("Could not fetch file from s3 public url: %s" % url)
        return False


def run(cmd, err=None, ok=None, quiet=False, user=None):
    """
    Convenience method for executing a shell command ``cmd``. Returns
    ``True`` if the command ran fine (i.e., exit code 0), ``False`` otherwise.

    In case of an error, include ``err`` in the log output;
    include ``ok`` output if command ran fine. If ``quiet`` is set to ``True``,
    do not log any messages.

    If `user` is set, run the command as the specified system user. Note that
    this may not work as expected if the command depends on embedded escaping
    of quotes or other special characters.
    """
    # Predefine err and ok mesages to include the command being run
    if err is None:
        err = "---> PROBLEM"
    if ok is None:
        ok = "'%s' command OK" % cmd
    if user:
        cmd = '/bin/su - {0} -c "{1}"'.format(user, cmd)
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, cwd=None)
    stdout, stderr = process.communicate()
    if process.returncode == 0:
        if not quiet:
            log.debug(ok)
        if stdout:
            return stdout
        else:
            return True
    else:
        if not quiet:
            log.error("%s, running command '%s' returned code '%s', the "
                      "following stderr: '%s' and stdout: '%s'"
                      % (err, cmd, process.returncode, stderr, stdout))
        return False


def getoutput(cmd, quiet=False, user=None):
    """
    Execute the shell command `cmd` and return the output.

    If `quiet` is set, do not log any messages. If there is an exception,
    return `None`. If `user` is set, run the command as the specified system
    user. Note that this may not work as expected if the command depends on
    embedded escaping of quotes or other special characters.
    """
    out = None
    try:
        if user:
            cmd = '/bin/su - {0} -c "{1}"'.format(user, cmd)
        out = commands.getoutput(cmd)
        if not quiet:
            log.debug("Executed command '{0}' and got output: {1}".format(cmd, out))
    except Exception, e:
        if not quiet:
            log.error("Exception executing command {0}: {1}".format(cmd, e))
    return out


def replace_string(file_name, pattern, subst):
    """
    Replace string ``pattern`` in file ``file_name`` with ``subst``.

    :type file_name: str
    :param file_name: Full path to the file where the string is to be replaced

    :type pattern: str
    :param pattern: String pattern to search for

    :type subst: str
    :param subst: String pattern to replace search pattern with
    """
    log.debug("Replacing string '{0}' with '{1}' in file {2}"
              .format(pattern, subst, file_name))
    try:
        # Create temp file
        fh, abs_path = mkstemp()
        new_file = open(abs_path, 'w')
        old_file = open(file_name)
        for line in old_file:
            new_file.write(line.replace(pattern, subst))
        # Close temp file
        new_file.close()
        os.close(fh)
        old_file.close()
        # Remove original file
        os.remove(file_name)
        # Move new file
        shutil.move(abs_path, file_name)
    except Exception, e:
        log.error("Trouble replacing string in file {0}: {1}".format(file_name, e))


def append_to_file(file_name, line):
    """
    Append ``line`` to ``file_name`` but only if not already present in the file.

    :type file_name: str
    :param file_name: Full path to the file where the line is to be appended

    :type line: str
    :param line: A line to be appended to the file
    """
    with open(file_name, 'a+') as f:
        if not any(line.strip() == x.rstrip('\r\n') for x in f):
            log.debug("Appending line '%s' to file %s" % (line, file_name))
            f.write(line + '\n')


def _if_not_installed(prog_name):
    """
    Decorator that checks if a callable program is installed.

    If not, the decorated method is called. If the program is
    installed, returns ``False``.
    """
    def argcatcher(func):
        def decorator(*args, **kwargs):
            log.debug("Checking if {0} is installed".format(prog_name))
            process = subprocess.Popen(
                prog_name, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            if process.returncode == 127:
                log.debug("{0} is *not* installed".format(prog_name))
                return func(*args, **kwargs)
            else:
                log.debug("{0} is installed".format(prog_name))
                return False
        return decorator
    return argcatcher


def set_hostname(hostname):
    """
    Set the instance hostname in `/etc/hostname`.

    :type hostname: string
    :param hostname: The value the hostname should be set to.
    """
    try:
        with open('/etc/hostname', 'w') as file_handle:
            file_handle.write("{0}\n".format(hostname))
        run('service hostname restart')
    except IOError, ioe:
        log.error("IOError wirting out /etc/hostname: {0}".format(ioe))


def get_hostname():
    """Return the output from ``hostname -s`` command."""
    try:
        return subprocess.check_output(["hostname", "-s"]).strip()
    except Exception:
        return ""


def make_dir(path, owner=None):
    """Check if a directory under ``path`` exists and create it if it does not."""
    log.debug("Checking existence of directory '%s'" % path)
    if not os.path.exists(path):
        try:
            log.debug("Creating directory '%s'" % path)
            os.makedirs(path, 0755)
            log.debug("Directory '%s' successfully created." % path)
            if owner:
                os.chown(path, pwd.getpwnam(owner)[2], grp.getgrnam(owner)[2])
                log.debug("Set dir '{0}' owner to {1}.".format(path, owner))
        except OSError, e:
            log.error("Making directory '%s' failed: %s" % (path, e))
    else:
        log.debug("Directory '%s' exists." % path)


def add_to_etc_hosts(ip_address, hosts=[]):
    """
    Add a line with the list of ``hosts`` for the given ``ip_address`` to
    ``/etc/hosts``.

    If a line with the provided ``ip_address`` already exist in the file, keep
    any existing hostnames and also add the otherwise not found new ``hosts``
    to the given line.
    """
    try:
        etc_hosts = open('/etc/hosts', 'r')
        # Pull out all the lines from /etc/hosts that do not have an entry
        # matching a value in `hosts` argument
        tmp = NamedTemporaryFile()
        existing_line = None
        for l in etc_hosts:
            contained = False
            for hostname in hosts:
                if hostname in l.split():
                    contained = True
            if ip_address and ip_address in l:
                contained = True
            if not contained:
                tmp.write(l)
            else:
                existing_line = l.strip()
        etc_hosts.close()
        if existing_line:
            ip_address = existing_line.split()[0]
            hostnames = existing_line.split()[1:]
            for hostname in hosts:
                if hostname not in hostnames:
                    hostnames.append(hostname)
            # Append new hosts to the exisiting line
            line = "{0} {1}\n".format(ip_address, ' '.join(hostnames))
        else:
            # Compose a new line with the hosts for the specified IP address
            line = '{0} {1}\n'.format(ip_address, ' '.join(hosts))
        tmp.write(line)
        # Make sure the changes are written to disk
        tmp.flush()
        os.fsync(tmp.fileno())
        # Swap out /etc/hosts
        run('cp /etc/hosts /etc/hosts.orig')
        run('cp {0} /etc/hosts'.format(tmp.name))
        run('chmod 644 /etc/hosts')
        log.debug("Added the following line to /etc/hosts: {0}".format(line))
    except (IOError, OSError) as e:
        log.error('Could not update /etc/hosts. {0}'.format(e))


def remove_from_etc_hosts(host):
    """Remove ``host`` (hostname or IP) from ``/etc/hosts``."""
    if not host:
        log.debug("Cannot remove empty host from /etc/hosts")
        return
    try:
        log.debug("Removing host {0} from /etc/hosts".format(host))
        etc_hosts = open('/etc/hosts', 'r')
        tmp = NamedTemporaryFile()
        for l in etc_hosts:
            if host not in l:
                tmp.write(l)
        etc_hosts.close()

        # make sure changes are written to disk
        tmp.flush()
        os.fsync(tmp.fileno())
        # swap out /etc/hosts
        run('cp /etc/hosts /etc/hosts.orig')
        run('cp {0} /etc/hosts'.format(tmp.name))
        run('chmod 644 /etc/hosts')
    except (IOError, OSError) as e:
        log.error('could not update /etc/hosts. {0}'.format(e))


def delete_file(path):
    """Check if a file at `path` exists and delete it."""
    if os.path.exists(path):
        log.debug("Deleting file {0}".format(path))
        os.remove(path)


class Sleeper(object):

    """
    Provides a 'sleep' method that sleeps for a number of seconds *unless*
    the notify method is called (from a different thread).
    """

    def __init__(self):
        self.condition = threading.Condition()

    def sleep(self, seconds):
        self.condition.acquire()
        self.condition.wait(seconds)
        self.condition.release()

    def wake(self):
        self.condition.acquire()
        self.condition.notify()
        self.condition.release()


def meminfo():
    """
    Get node total memory and memory usage by parsing `/proc/meminfo`.
    Return a dictionary with the following keys: `free`, `total`, `used`
    """
    with open('/proc/meminfo', 'r') as mem:
        ret = {}
        tmp = 0
        for i in mem:
            sline = i.split()
            if str(sline[0]) == 'MemTotal:':
                ret['total'] = int(sline[1])
            elif str(sline[0]) in ('MemFree:', 'Buffers:', 'Cached:'):
                tmp += int(sline[1])
        ret['free'] = tmp
        ret['used'] = int(ret['total']) - int(ret['free'])
    return ret


def get_dir_size(path):
    """
    Return the size of directory at `path` (and it's subdirectories), in bytes.
    """
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size


def nice_size(size):
    """
    Returns a readably formatted string with the size

    >>> nice_size(100)
    '100 bytes'
    >>> nice_size(10000)
    '9.8 KB'
    >>> nice_size(1000000)
    '976.6 KB'
    >>> nice_size(100000000)
    '95.4 MB'
    """
    words = ['bytes', 'KB', 'MB', 'GB', 'TB']
    try:
        size = float(size)
    except Exception:
        return 'N/A'
    for ind, word in enumerate(words):
        step = 1024 ** (ind + 1)
        if step > size:
            size = size / float(1024 ** ind)
            if word == 'bytes':  # No decimals for bytes
                return "%d bytes" % size
            return "%.1f %s" % (size, word)
    return 'N/A'


def size_to_bytes(size):
    """
    Returns a number of bytes if given a reasonably formatted string with the size
    """
    # Assume input in bytes if we can convert directly to an int
    try:
        return int(size)
    except Exception:
        return -1
    # Otherwise it must have non-numeric characters
    size_re = re.compile('([\d\.]+)\s*([tgmk]b?|b|bytes?)$')
    size_match = re.match(size_re, size.lower())
    assert size_match is not None
    size = float(size_match.group(1))
    multiple = size_match.group(2)
    if multiple.startswith('t'):
        return int(size * 1024 ** 4)
    elif multiple.startswith('g'):
        return int(size * 1024 ** 3)
    elif multiple.startswith('m'):
        return int(size * 1024 ** 2)
    elif multiple.startswith('k'):
        return int(size * 1024)
    elif multiple.startswith('b'):
        return int(size)


def detect_symlinks(dir_path, link_name=None, symlink_as_file=True):
    """
    Recursively walk the given directory looking for symlinks. Return
    a list of tuples containing the symlinks and the link targets (e.g.,
    (('/mnt/galaxyTools/tools/pass/default', '/mnt/galaxyTools/tools/pass/2.0'))).
    If the optional ``link_name`` is provided, return only symlinks with the
    given name. If ``symlink_as_file`` is set, treat symlinks as files;
    otherwise treat them as directories.
    If no symlink are found, return an empty list.
    """
    links = []
    for root, dirs, files in os.walk(dir_path):
        entities = files if symlink_as_file else dirs
        for entity in entities:
            path = os.path.join(root, entity)
            if os.path.islink(path):
                target_path = os.readlink(path)
                # Resolve relative symlinks
                if not os.path.isabs(target_path):
                    target_path = os.path.join(os.path.dirname(path), target_path)
                if not link_name:
                    links.append((path, target_path))
                elif entity == link_name:
                    links.append((path, target_path))
            else:
                # If it's not a symlink we're not interested.
                continue
    return links


def get_a_number():
    """
    This generator will yield a new integer each time it is called, starting
    at 1.
    """
    number = 1
    while True:
        yield number
        number += 1


def which(program, additional_paths=[]):
    """
    Like *NIX's ``which`` command, look for ``program`` in the user's $PATH
    and ``additional_paths`` to return an absolute path for the ``program``. If
    the ``program`` was not found, return ``None``.
    """
    def _is_exec(fpath):
        """Check if a file at `fpath` has the executable bit set."""
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if _is_exec(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep) + additional_paths:
            path = path.strip('"')
            exec_file = os.path.join(path, program)
            if _is_exec(exec_file):
                return exec_file
    return None


def run_psql_command(sql_command, user, psql_path, port=5432):
    """
    Given an `sql_command`, run the command using `psql` at `psql_path` for the
    given `user` on the specified `port`.
    """
    log.debug("Running {0}:{1} command for user {2}: {3}".format(psql_path,
              port, user, sql_command))
    return run('/bin/su - postgres -c "{0} -p {1} {2} -c \\\"{3}\\\" "'.format
               (psql_path, port, user, sql_command))


def random_string_generator(size=10, chars=string.ascii_uppercase + string.digits):
    """
    Generate a random string of `size` consisting of `chars`
    """
    return ''.join(random.choice(chars) for _ in range(size))


def write_template_file(template, parameters, conf_file):
    """
    Write out a file base on a string template.

    Given a `string.template` and appropriate `parameters` as a
    dict, load the file as a `string.Template`, substitute the `parameters` and
    write out the file to the `conf_file` path. Return `True` if successful,
    `False` otherwise.
    """
    try:
        t = template.substitute(parameters)
        # Write out the file
        with open(conf_file, 'w') as f:
            print >> f, t
        log.debug("Wrote template file {0}".format(conf_file))
        return True
    except KeyError, kexc:
        log.error("KeyError filling template {0}: {1}".format(template, kexc))
    except IOError, ioexc:
        log.error("IOError writing template file {0}: {1}".format(conf_file, ioexc))
    return False


class RingBuffer(object):

    """
    A class that implements a buffer with a fixed size, so that, when it fills
    up, adding another element overwrites the first (oldest) one.

    http://www.onlamp.com/lpt/a/5828
    """

    def __init__(self, size_max):
        self.max = size_max
        self.data = []

    class __Full(object):

        """Class that implements a full buffer."""

        def __init__(self):
            self.cur = 0

        def append(self, x):
            """Append an element overwriting the oldest one."""
            self.data[self.cur] = x
            self.cur = (self.cur + 1) % self.max

        def tolist(self):
            """Return list of elements in correct order."""
            return self.data[self.cur:] + self.data[:self.cur]

    def append(self, x):
        """Append an element at the end of the buffer."""
        self.data.append(x)
        if len(self.data) == self.max:
            self.cur = 0
            # Permanently change self's class from non-full to full
            self.__class__ = self.__Full

    def tolist(self):
        """Return a list of elements from the oldest to the newest."""
        return self.data
