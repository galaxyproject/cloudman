import re
import fileinput
from cm.util import templates

from cm.util import misc
from cm.util import paths
from cm.services import ServiceRole
from cm.services import service_states
from cm.services.apps import ApplicationService
from string import Template

import logging
log = logging.getLogger('cloudman')


class HTCondorService(ApplicationService):
    def __init__(self, app, srv_type, host=""):
        """
        the srv_type defines whether we are running a master node or a
        worker node. If we have run a worker the host IP should be passed
        in the host entry.
        """
        super(HTCondorService, self).__init__(app)
        log.debug("Condor is preparing")
        self.svc_roles = [ServiceRole.HTCONDOR]
        self.name = ServiceRole.to_string(ServiceRole.HTCONDOR)
        self.srv_type = srv_type
        if srv_type == "master":
            self.flock_to = ""
        else:
            self.host = host

    def start(self):
        """
        Set the user define configuration values and restart condor.
        """
        log.debug("Configuring Condor")
        self.state = service_states.STARTING
        self.configure_htcondor()

    def remove(self):
        """
        Shutting down Condor.
        """
        log.info("Shutting down HTCondor service")
        self.state = service_states.SHUTTING_DOWN
        misc.run("condor_off")
        self.state = service_states.SHUT_DOWN

    def configure_htcondor(self):
        """
        Configure environment for running HTCondor service over a node.
        """
        all_done = False
        try:
            log.debug("configuring condor")
            htcondor_params = {}
            if self.srv_type == "master":
                condor_template = Template(templates.HTCONDOR_MASTER_CONF_TEMPLATE)
                log.debug(condor_template)
                htcondor_params["flock_host"] = self.flock_to
            else:
                condor_template = Template(templates.HTCONDOR_WOORKER_CONF_TEMPLATE)
                htcondor_params = {
                    "host": self.host
                }
            log.debug(str(htcondor_params))
            condor_template = condor_template.substitute(htcondor_params)
            with open(paths.P_HTCONDOR_CONFIG_PATH, 'a') as f:
                print >> f, condor_template
            misc.run(paths.P_HTCONDOR_HOME + "/condor restart")
            all_done = True
            self.state = service_states.RUNNING
        except Exception, e:
            log.debug("Error while configuring HTCondor: {0}".format(e))
            self.state = service_states.ERROR
            all_done = False
        return all_done

    def modify_htcondor(self, key, value, action="a"):
        """
        Modifying HTCondor environment for running HTCondor as desired.
        It will restart HTCondor after modifying the configuration.
        The configuration format is in the form of a key value string pair
        and if the action passed as "a" then it will add the new value to the
        old value.
        """
        log.debug("modifying HTCondor")

        all_done = False
        try:
            default_val = self.find_config(key, '/etc/condor/condor_config')
            log.debug(default_val)
            val = ""
            if action == "a":
                if default_val != "":
                    val = value + "," + default_val
                else:
                    val = value
            else:
                val = value
            with open(paths.P_HTCONDOR_CONFIG_PATH, 'a') as f:
                print >> f, str(key) + "=" + str(val)
            misc.run(paths.P_HTCONDOR_HOME + "/condor restart")
            all_done = True
        except Exception, e:
            log.debug("Error while configuring HTCondor: {0}".format(e))
            all_done = False
            self.state = service_states.ERROR
        return all_done

    def status(self):
        """
        Check and update the status of HTCondor service. If the service state is
        ``SHUTTING_DOWN``, ``SHUT_DOWN``, ``UNSTARTED``, or ``WAITING_FOR_USER_ACTION``,
        the method doesn't do anything. Otherwise, it updates service status (see
        ``check_sge``) by setting ``self.state``, whose value is always the method's
        return value.
        """
        if self.state == service_states.RUNNING:
            return service_states.RUNNING
        else:
            pass

    def find_config(self, key, file, delim="="):
        """
        This function will look for the default/configured value of a key in the config file
        and return its value. It will return empty string if the key was not there. It will
        always return the last value found for a key this is because HTCondor accept the last
        value.

        This function should have been easily replaced with ConfigParser module's function
        from python but it only accept INI formatted and the community is praising it blindly doh.
        """
        if file is None:
            return -1
        default_val = ""
        for line in fileinput.input(file):
            #log.debug(line)
            if not line.strip():  # skip empty or space padded lines
                continue

            elif re.compile('^#').search(line) is not None:  # skip commented lines
                continue
            else:  # pick up key and value pairs
                if '=' in line:
                    tmpkey = line.strip().split(delim)[0].strip()
                if key == tmpkey:
                    default_val = '='.join(line.strip().split(delim)[1:])
        return default_val
