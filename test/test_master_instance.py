from unittest import TestCase

from cm.util.master import Instance
from cm.util.master import TIME_IN_PAST
from cm.util import instance_states

from test_utils import TestApp
from test_utils import MockBotoInstance
from test_utils import DEFAULT_MOCK_BOTO_INSTANCE_ID


class MasterInstanceTestCase(TestCase):

    def setUp(self):
        self.app = TestApp()
        self.inst = MockBotoInstance()
        self.instance = Instance(self.app, inst=self.inst)

    def test_id(self):
        assert self.instance.id == DEFAULT_MOCK_BOTO_INSTANCE_ID

    def test_get_cloud_instance_object(self):
        instance = self.instance

        # Without deep=True, just returned cached boto inst object.
        assert instance.get_cloud_instance_object() is self.inst

        # With deep=True should fetch new instance.
        fresh_instance = self.__seed_fresh_instance()
        assert instance.get_cloud_instance_object(deep=True) is fresh_instance

    def test_get_m_state(self):
        assert self.instance.m_state == None
        fresh_instance = self.__seed_fresh_instance()
        fresh_instance.state = instance_states.RUNNING
        assert self.instance.get_m_state() == instance_states.RUNNING
        assert self.instance.m_state == instance_states.RUNNING

    def test_reboot(self):
        """
        Check reboot was called on boto instance, time_rebooted is
        updated, and reboot_count is incremeneted.
        """
        assert self.instance.time_rebooted is TIME_IN_PAST
        assert self.instance.reboot_count == 0
        self.instance.reboot()
        assert self.inst.was_rebooted
        assert self.instance.time_rebooted is not TIME_IN_PAST
        assert self.instance.reboot_count == 1

        # Check successive calls continue to increment reboot_count.
        self.instance.reboot()
        assert self.instance.reboot_count == 2

    def test_terminate_success(self):
        self.app.cloud_interface.expect_terminatation( \
            DEFAULT_MOCK_BOTO_INSTANCE_ID, spot_request_id=None, success=True)
        assert self.instance.terminate_attempt_count == 0
        assert self.instance.inst is not None
        thread = self.instance.terminate()
        thread.join()
        assert self.instance.inst is None
        assert self.instance.terminate_attempt_count == 1

    def test_terminate_failure(self):
        self.app.cloud_interface.expect_terminatation( \
            DEFAULT_MOCK_BOTO_INSTANCE_ID, spot_request_id=None, success=False)
        assert self.instance.terminate_attempt_count == 0
        self.__seed_fresh_instance()   # Needed for log statement in failure
        thread = self.instance.terminate()
        thread.join()
        # inst is only set to None after success
        assert self.instance.inst is not None
        assert self.instance.terminate_attempt_count == 1

    def test_maintain(self):
        self.instance.maintain()

    def __seed_fresh_instance(self):
        fresh_instance = MockBotoInstance()
        self.app.cloud_interface.set_mock_instances([fresh_instance])
        return fresh_instance
