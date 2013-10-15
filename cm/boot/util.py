import subprocess
import os


def _run(log, cmd):
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode == 0:
        log.debug("Successfully ran '%s'" % cmd)
        if stdout:
            return stdout
        else:
            return True
    else:
        log.error("Error running '%s'. Process returned code '%s' and following stderr: %s" %
            (cmd, process.returncode, stderr))
        return False


def _is_running(log, process_name):
    """
    Check if a process with ``process_name`` is running. Return ``True`` is so,
    ``False`` otherwise.
    """
    p = _run(log, "ps xa | grep {0} | grep -v grep".format(process_name))
    return p and process_name in p


def _make_dir(log, path):
    log.debug("Checking existence of directory '%s'" % path)
    if not os.path.exists(path):
        try:
            log.debug("Creating directory '%s'" % path)
            os.makedirs(path, 0755)
            log.debug("Directory '%s' successfully created." % path)
        except OSError, e:
            log.error("Making directory '%s' failed: %s" % (path, e))
    else:
        log.debug("Directory '%s' exists." % path)
