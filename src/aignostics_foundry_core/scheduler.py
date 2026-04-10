"""Scheduler abstractions — BaseJoblet for Chancy-backed job modules."""

import asyncio

from chancy import Chancy, Job, Queue
from chancy.plugins.cron import Cron
from chancy.plugins.trigger import Trigger
from loguru import logger


class BaseJoblet:
    """Base class for joblets that can be auto-registered with the scheduler.

    Implement one or all of get_queues, get_jobs, and get_crons to define the joblet's behavior.

    Note: For advanced use cases, you can implement special handling when registering or unregistering,
    override the respective methods.
    """

    @staticmethod
    def get_queues() -> list[Queue]:
        """
        Get queues for this joblet.

        Subclasses can override this method to return custom queues with specific
        configurations (concurrency, rate limits, etc.).

        Returns:
            list[Queue]: List of Queue instances to declare. Empty list by default.
        """
        return []

    @staticmethod
    def get_jobs() -> list[Job]:
        """
        Get one-time or scheduled jobs for this joblet.

        Subclasses can override this method to return jobs that should be pushed
        to the scheduler (e.g., one-time jobs with scheduled_at, jobs with delays).

        Returns:
            list[Job]: List of Job instances to push. Empty list by default.
        """
        return []

    @staticmethod
    def get_crons() -> list[tuple[str, Job]]:
        """
        Get cron jobs for this joblet.

        This method should be implemented by subclasses to return their cron schedules.

        Returns:
            list[tuple[str, Job]]: List of tuples containing (cron_expression, job).
                                   Example: [("* * * * *", my_job.job.with_unique_key("my_cron"))]
        """
        return []

    @staticmethod
    def get_triggers() -> list[
        tuple[
            str,
            list[str],
            Job,
        ]
    ]:
        """
        Get trigger jobs for this joblet.

        This method should be implemented by subclasses to return their trigger configurations.

        Returns:
            list[tuple[str, list[str], Job]]: List of tuples containing (table_name, operations, job_template).
                                   Example: [("my_table", ["INSERT", "UPDATE"], my_job)]
        """
        return []

    async def register_queues(self, chancy: Chancy) -> None:
        """
        Register queues with the scheduler.

        Args:
            chancy: The Chancy instance to register queues with.
        """
        for queue in self.get_queues():
            logger.trace("Joblet {} registering queue '{}'.", self.key(), queue.name)
            await chancy.declare(queue, upsert=True)
            logger.debug("Joblet {} registered queue '{}' with state {}.", self.key(), queue.name, queue.state)

    async def register_jobs(self, chancy: Chancy) -> None:
        """
        Register jobs with the scheduler.

        Args:
            chancy: The Chancy instance to register jobs with.
        """
        for job in self.get_jobs():
            logger.trace("Joblet {} pushing job '{}'.", self.key(), job)
            reference = await chancy.push(job)
            logger.debug(
                "Joblet {} registered job {} with reference {}.",
                self.key(),
                job,
                reference,
            )

    async def register_crons(self, chancy: Chancy) -> None:
        """
        Register cron jobs with the scheduler.

        Args:
            chancy: The Chancy instance to register cron jobs with.
        """
        for cron_expression, job in self.get_crons():
            logger.trace(
                "Joblet {} scheduling cron job with expression '{}' and unique key '{}'.",
                self.key(),
                cron_expression,
                job.unique_key,
            )
            if not job.unique_key:
                logger.warning(
                    "Joblet {} tried to schedule cron job without unique key - scheduling skipped",
                    self.key(),
                )
                continue
            await Cron.schedule(chancy, cron_expression, job)  # pyright: ignore[reportUnknownMemberType]
            logger.debug(
                "Joblet {} scheduled cron job with expression '{}' and unique key '{}'.",
                self.key(),
                cron_expression,
                job.unique_key,
            )

    async def register_triggers(self, chancy: Chancy) -> None:
        """
        Register trigger jobs with the scheduler.

        Args:
            chancy: The Chancy instance to register trigger jobs with.
        """
        triggers_to_register = self.get_triggers()
        if not triggers_to_register:
            return
        triggers = await Trigger.get_triggers(chancy)
        logger.trace("Found existing triggers: {}", triggers)
        for table_name, operations, job_template in triggers_to_register:
            logger.trace(
                "Joblet {} registering trigger for table name '{}', operations '{}', and job template '{}'.",
                self.key(),
                table_name,
                operations,
                job_template,
            )
            for trigger_id, trigger_config in triggers.items():
                if (
                    trigger_config.table_name == table_name
                    and set(trigger_config.operations) == set(operations)
                    and trigger_config.job_template.func == job_template.func
                ):
                    logger.debug(
                        "Joblet {} found existing trigger with id '{}' for table name '{}', "
                        "operations '{}', and job template '{}'. Skipping registration.",
                        self.key(),
                        trigger_id,
                        table_name,
                        operations,
                        job_template,
                    )
                    break
            else:
                trigger_id = await Trigger.register_trigger(  # pyright: ignore[reportUnknownMemberType]
                    chancy=chancy, table_name=table_name, operations=operations, job_template=job_template
                )
                logger.debug(
                    "Joblet {} registered trigger with id '{}' for table name '{}', "
                    "operations '{}', and job template '{}'.",
                    self.key(),
                    trigger_id,
                    table_name,
                    operations,
                    job_template,
                )

    async def unregister_queues(self, chancy: Chancy, purge_jobs: bool = True) -> None:
        """
        Unregister queues from the scheduler.

        Args:
            chancy: The Chancy instance to unregister queues from.
            purge_jobs: Whether to purge all jobs from the queue before deletion.
        """
        for queue in self.get_queues():
            logger.trace("Joblet {} unregistering queue '{}'.", self.key(), queue.name)
            await chancy.delete_queue(queue.name, purge_jobs=purge_jobs)
            logger.debug("Joblet {} unregistered queue '{}'.", self.key(), queue.name)

    async def unregister_jobs(self, chancy: Chancy) -> None:
        """
        Unregister jobs from the scheduler.

        This removes jobs that were pushed with unique keys.
        Note: Currently no-op as Chancy doesn't provide delete_job API.

        Args:
            chancy: The Chancy instance to unregister jobs from.
        """
        # TODO(helmut): Implement when Chancy provides delete_job API
        _ = chancy
        await asyncio.sleep(0)  # SonarQube wants this function to do something async
        logger.warning(
            "Joblet {} unregister_jobs called, but not implemented as Chancy does not provide delete_job API.",
            self.key(),
        )

    async def unregister_crons(self, chancy: Chancy) -> None:
        """
        Unregister cron jobs from the scheduler.

        This removes cron schedules that were registered with unique keys.

        Args:
            chancy: The Chancy instance to unregister cron jobs from.
        """
        for _, job in self.get_crons():
            if job.unique_key:
                logger.trace("Joblet {} unregistering cron job with unique key '{}'.", self.key(), job.unique_key)
                await Cron.unschedule(chancy, job.unique_key)
                logger.debug("Joblet {} unregistered cron job with unique key '{}'.", self.key(), job.unique_key)
            else:
                logger.critical(
                    "When unregistering crons Joblet {} found cron job without unique key - this must not happen.",
                    self.key(),
                )

    async def unregister_triggers(self, chancy: Chancy) -> None:
        """
        Unregister trigger jobs from the scheduler.

        This removes triggers that were registered by this joblet.

        Args:
            chancy: The Chancy instance to unregister trigger jobs from.
        """
        triggers = await Trigger.get_triggers(chancy)
        for table_name, operations, job_template in self.get_triggers():
            logger.trace(
                "Joblet {} unregistering trigger for table name '{}', operations '{}', and job template '{}'.",
                self.key(),
                table_name,
                operations,
                job_template,
            )
            unregistered = False
            for trigger_id, trigger_config in triggers.items():
                if (
                    trigger_config.table_name == table_name
                    and set(trigger_config.operations) == set(operations)
                    and trigger_config.job_template.func == job_template.func
                ):
                    await Trigger.unregister_trigger(chancy, trigger_id)
                    unregistered = True
                    logger.debug(
                        "Joblet {} unregistered trigger with id '{}' for table name '{}', "
                        "operations '{}', and job template '{}'.",
                        self.key(),
                        trigger_id,
                        table_name,
                        operations,
                        job_template,
                    )
            if not unregistered:
                logger.debug(
                    "Joblet {} found no matching trigger to unregister for table name '{}', "
                    "operations '{}', and job template '{}'.",
                    self.key(),
                    table_name,
                    operations,
                    job_template,
                )

    @classmethod
    def key(cls) -> str:
        """
        Return the module name of the joblet class.

        Returns:
            str: Module name (e.g., 'hello_world' for bridge.hello_world.Joblet).
        """
        return cls.__module__.split(".")[-2]
