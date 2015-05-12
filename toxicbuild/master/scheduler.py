# -*- coding: utf-8 -*-

# Copyright 2015 Juca Crispim <juca@poraodojuca.net>

# This file is part of toxicbuild.

# toxicbuild is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# toxicbuild is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with toxicbuild. If not, see <http://www.gnu.org/licenses/>.

import time
import asyncio


__doc__ = """
A very simple implementation of a in memory task scheduler using asyncio.
"""


class PeriodicTask:

    """ A task that will be executed in a periodic time interval
    """

    def __init__(self, coro, interval):
        """:param coro: coroutine to be consumed at ``ìnterval``.
        :param interval: Time in seconds to consume the coroutine.
        """
        self.coro = coro
        self.interval = interval


class TaskScheduler:

    """ A simple scheduler for periodic tasks.
    """

    def __init__(self):
        # self.tasks has the format {hash(task_call_or_coro): task}
        self.tasks = {}

        # self.consumption_table has the format {task: last_consumption}
        self.consumption_table = {}

        self._stop = False
        self._started = False

    def add(self, task_call_or_coro, interval):
        """ Adds ``task_call_or_coro`` to be consumed at ``interval``.

        :param task_call_or_coro: callable or coroutine to be consumed.
        :param interval: time in seconds to consume task_call_or_coro.
        """

        coro = task_call_or_coro
        if not asyncio.coroutines.iscoroutine(task_call_or_coro):
            coro = asyncio.coroutine(task_call_or_coro)

        task = PeriodicTask(coro, interval)

        self.tasks[hash(task_call_or_coro)] = task

        # timestamp 0 for the task to be consumed on firt time
        self.consumption_table[task] = 0.0

    def remove(self, task_call_or_coro):
        """ Removes ``task_call_or_coro`` from the scheduler
        :param task_call_or_coro: callable or coroutine to remove
        """
        cc_hash = hash(task_call_or_coro)
        task = self.tasks[cc_hash]
        del self.consumption_table[task]
        del self.tasks[cc_hash]

    def consume_tasks(self):
        now = time.time()
        # all tasks that is time to consume again
        tasks2consume = [task for task, t in self.consumption_table.items()
                         if t + task.interval <= now]

        for task in tasks2consume:
            self.consumption_table[task] = now
            asyncio.async(task.coro())

    @asyncio.coroutine
    def start(self):
        if self._started:  # pragma: no cover
            return

        self._started = True

        while not self._stop:
            self.consume_tasks()
            yield from asyncio.sleep(1)

        self._started = False

    def stop(self):
        self._stop = True

scheduler = TaskScheduler()
scheduler.start()
