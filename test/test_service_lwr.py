from cm.services.apps.lwr import LwrService, INVOKE_SUCCESS, INVOKE_FAILURE
from test_utils import TestApp, mock_runner

from mock import call


def test_lwr_service():
    test_app = TestApp()
    with mock_runner() as runner:
        service = LwrService(test_app)
        service.start()
        start_cmd = '/bin/su - galaxy -c "bash %s/run.sh --daemon"' % test_app.path_resolver.lwr_home
        calls = runner.call_args_list
        assert call(start_cmd, INVOKE_FAILURE, INVOKE_SUCCESS) in calls, \
            "no call of %s in %s" % (start_cmd, calls)
