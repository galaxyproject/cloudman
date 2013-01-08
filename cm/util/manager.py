"""Implement base class for worker and master ConsoleManagers"""

from cm.util import misc


class BaseConsoleManager(object):
    """ Super class for master and worker ConsoleManagers """

    def _handle_prestart_commands(self):
        """
        Inspect the user data key (either ``master_prestart_commands`` or
        ``worker_prestart_commands`` depending on node type and simply execute
        any commands provided there.

        For example::
            master_prestart_commands:
              - "mkdir -p /mnt/galaxyData/pgsql/"
              - "mkdir -p /mnt/galaxyData/tmp"
              - "chown -R galaxy:galaxy /mnt/galaxyData"
        """
        user_data_variable = "%s_prestart_commands" % self.node_type #NGTODO: Another potential hardcoded link to galaxyData?
        for command in self.app.ud.get(user_data_variable, []):
            misc.run(command)
