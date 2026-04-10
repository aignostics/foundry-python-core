"""Tests for scheduler module — BaseJoblet behaviour."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from chancy import Chancy, Job, Queue

from aignostics_foundry_core.scheduler import BaseJoblet

QUEUE_NAME = "test_queue"
CRON_EXPRESSION = "* * * * *"
UNIQUE_KEY = "my_cron"
JOB_UNIQUE_KEY = "my_job"
TABLE_NAME = "my_table"
TABLE_NAME_2 = "other_table"
OPERATIONS = ["INSERT", "UPDATE"]
TRIGGER_ID = "tid-1"


class _QueueJoblet(BaseJoblet):
    """Joblet that declares a single named queue."""

    @staticmethod
    def get_queues() -> list[Queue]:
        return [Queue(QUEUE_NAME)]


class _JobJoblet(BaseJoblet):
    """Joblet that declares a single job."""

    @staticmethod
    def get_jobs() -> list[Job]:
        return [MagicMock(spec=Job)]


def _make_trigger_joblet(job_template: Job) -> BaseJoblet:
    """Return a BaseJoblet instance whose get_triggers() yields the given job_template."""

    class _TriggerJoblet(BaseJoblet):
        @staticmethod
        def get_triggers() -> list[tuple[str, list[str], Job]]:
            return [(TABLE_NAME, OPERATIONS, job_template)]

    return _TriggerJoblet()


def _make_cron_joblet(job: Job) -> BaseJoblet:
    """Return a BaseJoblet instance whose get_crons() yields the given job."""

    class _CronJoblet(BaseJoblet):
        @staticmethod
        def get_crons() -> list[tuple[str, Job]]:
            return [(CRON_EXPRESSION, job)]

    return _CronJoblet()


class TestDefaultHooks:
    """Tests for BaseJoblet default hook return values."""

    @pytest.mark.unit
    def test_get_queues_returns_empty_list(self) -> None:
        """get_queues() returns an empty list by default."""
        assert BaseJoblet().get_queues() == []

    @pytest.mark.unit
    def test_get_jobs_returns_empty_list(self) -> None:
        """get_jobs() returns an empty list by default."""
        assert BaseJoblet().get_jobs() == []

    @pytest.mark.unit
    def test_get_crons_returns_empty_list(self) -> None:
        """get_crons() returns an empty list by default."""
        assert BaseJoblet().get_crons() == []


class TestRegisterJobs:
    """Tests for BaseJoblet.register_jobs()."""

    @pytest.mark.unit
    async def test_register_jobs_pushes_each_job(self) -> None:
        """register_jobs calls chancy.push once for each job returned by get_jobs()."""
        joblet = _JobJoblet()
        mock_chancy = MagicMock(spec=Chancy)
        mock_chancy.push = AsyncMock(return_value="ref")

        await joblet.register_jobs(mock_chancy)

        assert mock_chancy.push.call_count == 1
        pushed_job = mock_chancy.push.call_args.args[0]
        assert isinstance(pushed_job, MagicMock)


class TestRegisterQueues:
    """Tests for BaseJoblet.register_queues()."""

    @pytest.mark.unit
    async def test_register_queues_declares_each_queue(self) -> None:
        """register_queues calls chancy.declare once per queue with upsert=True."""
        joblet = _QueueJoblet()
        mock_chancy = MagicMock(spec=Chancy)
        mock_chancy.declare = AsyncMock()

        await joblet.register_queues(mock_chancy)

        assert mock_chancy.declare.call_count == 1
        call_args = mock_chancy.declare.call_args
        assert call_args.args[0].name == QUEUE_NAME
        assert call_args.kwargs == {"upsert": True}


class TestRegisterCrons:
    """Tests for BaseJoblet.register_crons()."""

    @pytest.mark.unit
    async def test_register_crons_skips_job_without_unique_key(self) -> None:
        """register_crons never calls Cron.schedule when job.unique_key is falsy."""
        job = MagicMock(spec=Job)
        job.unique_key = None
        joblet = _make_cron_joblet(job)
        mock_chancy = MagicMock(spec=Chancy)

        with patch("aignostics_foundry_core.scheduler.Cron.schedule", new_callable=AsyncMock) as mock_schedule:
            await joblet.register_crons(mock_chancy)

        mock_schedule.assert_not_called()

    @pytest.mark.unit
    async def test_register_crons_schedules_job_with_unique_key(self) -> None:
        """register_crons calls Cron.schedule with (chancy, expression, job) when unique_key is set."""
        job = MagicMock(spec=Job)
        job.unique_key = UNIQUE_KEY
        joblet = _make_cron_joblet(job)
        mock_chancy = MagicMock(spec=Chancy)

        with patch("aignostics_foundry_core.scheduler.Cron.schedule", new_callable=AsyncMock) as mock_schedule:
            await joblet.register_crons(mock_chancy)

        mock_schedule.assert_called_once_with(mock_chancy, CRON_EXPRESSION, job)


class TestRegisterTriggers:
    """Tests for BaseJoblet.register_triggers()."""

    @pytest.mark.unit
    async def test_register_triggers_is_noop_when_no_triggers(self) -> None:
        """register_triggers returns early without calling Trigger.get_triggers when get_triggers() is empty."""
        joblet = BaseJoblet()
        mock_chancy = MagicMock(spec=Chancy)

        with patch("aignostics_foundry_core.scheduler.Trigger.get_triggers", new_callable=AsyncMock) as mock_get:
            await joblet.register_triggers(mock_chancy)

        mock_get.assert_not_called()

    @pytest.mark.unit
    async def test_register_triggers_registers_new_trigger(self) -> None:
        """register_triggers calls Trigger.register_trigger when no matching trigger exists."""
        job_template = MagicMock()
        joblet = _make_trigger_joblet(job_template)
        mock_chancy = MagicMock(spec=Chancy)

        with (
            patch("aignostics_foundry_core.scheduler.Trigger.get_triggers", new_callable=AsyncMock) as mock_get,
            patch("aignostics_foundry_core.scheduler.Trigger.register_trigger", new_callable=AsyncMock) as mock_reg,
        ):
            mock_get.return_value = {}
            await joblet.register_triggers(mock_chancy)

        mock_reg.assert_called_once_with(
            chancy=mock_chancy, table_name=TABLE_NAME, operations=OPERATIONS, job_template=job_template
        )

    @pytest.mark.unit
    async def test_register_triggers_handles_multiple_triggers(self) -> None:
        """register_triggers registers only non-matching triggers when multiple are configured."""
        job1 = MagicMock()
        job2 = MagicMock()

        class _MultiTriggerJoblet(BaseJoblet):
            @staticmethod
            def get_triggers() -> list[tuple[str, list[str], Job]]:
                return [(TABLE_NAME, OPERATIONS, job1), (TABLE_NAME_2, OPERATIONS, job2)]

        joblet = _MultiTriggerJoblet()
        mock_chancy = MagicMock(spec=Chancy)

        mock_config = MagicMock()
        mock_config.table_name = TABLE_NAME
        mock_config.operations = list(OPERATIONS)
        mock_config.job_template.func = job1.func

        with (
            patch("aignostics_foundry_core.scheduler.Trigger.get_triggers", new_callable=AsyncMock) as mock_get,
            patch("aignostics_foundry_core.scheduler.Trigger.register_trigger", new_callable=AsyncMock) as mock_reg,
        ):
            mock_get.return_value = {TRIGGER_ID: mock_config}
            await joblet.register_triggers(mock_chancy)

        mock_reg.assert_called_once_with(
            chancy=mock_chancy, table_name=TABLE_NAME_2, operations=OPERATIONS, job_template=job2
        )

    @pytest.mark.unit
    async def test_register_triggers_skips_existing_matching_trigger(self) -> None:
        """register_triggers does not call Trigger.register_trigger when a matching trigger exists."""
        job_template = MagicMock()
        joblet = _make_trigger_joblet(job_template)
        mock_chancy = MagicMock(spec=Chancy)

        mock_config = MagicMock()
        mock_config.table_name = TABLE_NAME
        mock_config.operations = list(OPERATIONS)
        mock_config.job_template.func = job_template.func

        with (
            patch("aignostics_foundry_core.scheduler.Trigger.get_triggers", new_callable=AsyncMock) as mock_get,
            patch("aignostics_foundry_core.scheduler.Trigger.register_trigger", new_callable=AsyncMock) as mock_reg,
        ):
            mock_get.return_value = {TRIGGER_ID: mock_config}
            await joblet.register_triggers(mock_chancy)

        mock_reg.assert_not_called()


class TestUnregisterQueues:
    """Tests for BaseJoblet.unregister_queues()."""

    @pytest.mark.unit
    async def test_unregister_queues_calls_delete_queue(self) -> None:
        """unregister_queues calls chancy.delete_queue with correct name and purge_jobs=True."""
        joblet = _QueueJoblet()
        mock_chancy = MagicMock(spec=Chancy)
        mock_chancy.delete_queue = AsyncMock()

        await joblet.unregister_queues(mock_chancy)

        mock_chancy.delete_queue.assert_called_once_with(QUEUE_NAME, purge_jobs=True)


class TestUnregisterJobs:
    """Tests for BaseJoblet.unregister_jobs()."""

    @pytest.mark.unit
    async def test_unregister_jobs_completes_without_error(self) -> None:
        """unregister_jobs runs to completion without raising an exception."""
        await BaseJoblet().unregister_jobs(MagicMock(spec=Chancy))


class TestUnregisterCrons:
    """Tests for BaseJoblet.unregister_crons()."""

    @pytest.mark.unit
    async def test_unregister_crons_unschedules_job_with_unique_key(self) -> None:
        """unregister_crons calls Cron.unschedule with the job's unique_key."""
        job = MagicMock(spec=Job)
        job.unique_key = UNIQUE_KEY
        joblet = _make_cron_joblet(job)
        mock_chancy = MagicMock(spec=Chancy)

        with patch("aignostics_foundry_core.scheduler.Cron.unschedule", new_callable=AsyncMock) as mock_unschedule:
            await joblet.unregister_crons(mock_chancy)

        mock_unschedule.assert_called_once_with(mock_chancy, UNIQUE_KEY)

    @pytest.mark.unit
    async def test_unregister_crons_skips_job_without_unique_key(self) -> None:
        """unregister_crons does not call Cron.unschedule when job has no unique_key."""
        job = MagicMock(spec=Job)
        job.unique_key = None
        joblet = _make_cron_joblet(job)
        mock_chancy = MagicMock(spec=Chancy)

        with patch("aignostics_foundry_core.scheduler.Cron.unschedule", new_callable=AsyncMock) as mock_unschedule:
            await joblet.unregister_crons(mock_chancy)

        mock_unschedule.assert_not_called()


class TestUnregisterTriggers:
    """Tests for BaseJoblet.unregister_triggers()."""

    @pytest.mark.unit
    async def test_unregister_triggers_unregisters_matching_trigger(self) -> None:
        """unregister_triggers calls Trigger.unregister_trigger with the matching trigger ID."""
        job_template = MagicMock()
        joblet = _make_trigger_joblet(job_template)
        mock_chancy = MagicMock(spec=Chancy)

        mock_config = MagicMock()
        mock_config.table_name = TABLE_NAME
        mock_config.operations = list(OPERATIONS)
        mock_config.job_template.func = job_template.func

        with (
            patch("aignostics_foundry_core.scheduler.Trigger.get_triggers", new_callable=AsyncMock) as mock_get,
            patch("aignostics_foundry_core.scheduler.Trigger.unregister_trigger", new_callable=AsyncMock) as mock_unreg,
        ):
            mock_get.return_value = {TRIGGER_ID: mock_config}
            await joblet.unregister_triggers(mock_chancy)

        mock_unreg.assert_called_once_with(mock_chancy, TRIGGER_ID)

    @pytest.mark.unit
    async def test_unregister_triggers_logs_when_no_matching_trigger(self) -> None:
        """unregister_triggers does not call Trigger.unregister_trigger when no trigger matches."""
        job_template = MagicMock()
        joblet = _make_trigger_joblet(job_template)
        mock_chancy = MagicMock(spec=Chancy)

        mock_config = MagicMock()
        mock_config.table_name = "other_table"
        mock_config.operations = list(OPERATIONS)
        mock_config.job_template.func = job_template.func

        with (
            patch("aignostics_foundry_core.scheduler.Trigger.get_triggers", new_callable=AsyncMock) as mock_get,
            patch("aignostics_foundry_core.scheduler.Trigger.unregister_trigger", new_callable=AsyncMock) as mock_unreg,
        ):
            mock_get.return_value = {TRIGGER_ID: mock_config}
            await joblet.unregister_triggers(mock_chancy)

        mock_unreg.assert_not_called()


class TestKey:
    """Tests for BaseJoblet.key()."""

    @pytest.mark.unit
    def test_key_returns_second_to_last_module_component(self) -> None:
        """key() returns the second-to-last dotted segment of the subclass __module__."""

        class _LocalJoblet(BaseJoblet):
            pass

        expected = _LocalJoblet.__module__.split(".")[-2]
        assert _LocalJoblet.key() == expected
        assert len(_LocalJoblet.key()) > 0
