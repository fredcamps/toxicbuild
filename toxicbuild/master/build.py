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


import asyncio
from collections import defaultdict, deque
import datetime
from mongomotor import Document, EmbeddedDocument
from mongomotor.fields import (StringField, ListField, EmbeddedDocumentField,
                               ReferenceField, DateTimeField, BooleanField,
                               IntField)
from tornado.platform.asyncio import to_asyncio_future
from toxicbuild.core.utils import log
from toxicbuild.master.client import get_build_client
from toxicbuild.master.signals import (build_started, build_finished,
                                       revision_added, step_started,
                                       step_finished)


class Builder(Document):

    """ The entity responsible for execute the build steps
    """

    name = StringField()
    repository = ReferenceField('toxicbuild.master.Repository')

    @classmethod
    @asyncio.coroutine
    def create(cls, **kwargs):
        repo = cls(**kwargs)
        yield from to_asyncio_future(repo.save())
        return repo

    @classmethod
    @asyncio.coroutine
    def get(cls, **kwargs):
        builder = yield from to_asyncio_future(cls.objects.get(**kwargs))
        return builder


class BuildStep(EmbeddedDocument):

    """ A step for build
    """
    name = StringField(required=True)
    command = StringField(required=True)
    status = StringField(required=True)
    output = StringField()
    started = DateTimeField()
    finished = DateTimeField()


class Build(Document):

    """ A set of steps for a repository
    """

    PENDING = 'pending'

    repository = ReferenceField('toxicbuild.master.Repository', required=True)
    slave = ReferenceField('Slave', required=True)
    branch = StringField(required=True)
    named_tree = StringField(required=True)
    started = DateTimeField()
    finished = DateTimeField()
    builder = ReferenceField(Builder, required=True)
    status = StringField(default=PENDING)
    steps = ListField(EmbeddedDocumentField(BuildStep))

    @asyncio.coroutine
    def get_parallels(self):
        """ Returns builds that can be executed in parallel.

        Builds that can be executed in parallel are those that have the
        same branch and named_tree, but different builders.

        This method returns the parallels builds for the same slave and
        repository of this build.
        """

        parallels = type(self).objects.filter(
            id__ne=self.id, branch=self.branch, named_tree=self.named_tree,
            builder__ne=self.builder, slave=self.slave)
        parallels = yield from to_asyncio_future(parallels.to_list())
        return parallels


class Slave(Document):

    """ Slaves are the entities that actualy do the work
    of execute steps. The comunication to slaves is through
    the network (using :class:`toxicbuild.master.client.BuildClient`)
    and all code, including toxicbuild.conf, is executed on slave.
    """
    name = StringField(required=True, unique=True)
    host = StringField(required=True)
    port = IntField(required=True)
    is_alive = BooleanField(default=False)

    @classmethod
    @asyncio.coroutine
    def create(cls, **kwargs):
        slave = cls(**kwargs)
        yield from to_asyncio_future(slave.save())
        return slave

    @classmethod
    @asyncio.coroutine
    def get(cls, **kwargs):
        slave = yield from to_asyncio_future(cls.objects.get(**kwargs))
        return slave

    @asyncio.coroutine
    def get_client(self):
        """ Returns a :class:`toxicbuild.master.client.BuildClient` instance
        already connected to the server.
        """
        connected_client = yield from get_build_client(self.host, self.port)
        return connected_client

    @asyncio.coroutine
    def healthcheck(self):
        """ Check if the build server is up and running
        """
        with (yield from self.get_client()) as client:
            alive = yield from client.healthcheck()

        self.is_alive = alive
        # using yield instead of yield from because mongomotor's
        # save returns a tornado Future, not a asyncio Future
        yield from to_asyncio_future(self.save())
        return self.is_alive

    @asyncio.coroutine
    def list_builders(self, revision):
        """ List builder available in for a given revision

        :param revision: An instance of
          :class:`toxicbuild.master.repositories.RepositoryRevision`
        """
        repository = yield from to_asyncio_future(revision.repository)
        repo_url = repository.url
        vcs_type = repository.vcs_type
        branch = revision.branch
        named_tree = revision.commit

        with (yield from self.get_client()) as client:
            builders = yield from client.list_builders(repo_url, vcs_type,
                                                       branch, named_tree)

        builders = yield from [
            (yield from Builder.get(repository=repository, name=bname))
            for bname in builders]
        return list(builders)

    @asyncio.coroutine
    def build(self, build):
        """ Connects to a build server and requests a build on that server

        :param build: An instance of :class:`toxicbuild.master.build.Build`
        """

        # messy method! not so sure if this works! be careful! sorry!
        # It supposedly works as follows:
        # client.build() is a generator, each iteration returns a info about
        # the build. It sends 2 infos about steps, when it is started and when
        # it is finished and the last respose from the server is the
        # info about the build itself.
        repository = yield from to_asyncio_future(build.repository)

        with (yield from self.get_client()) as client:
            builder_name = (yield from to_asyncio_future(build.builder)).name
            for build_info in client.build(repository.url, repository.vcs_type,
                                           build.branch, build.named_tree,
                                           builder_name):

                # Ahhh! bad place for step time stuff. Need to put it on
                # slave
                build.started = datetime.datetime.now()
                build.status = 'running'
                yield from to_asyncio_future(build.save())
                build_started.send(self, build=build)

                # response with total_steps is the last one
                if 'total_steps' in build_info:
                    break

                step = yield from self._get_step(build, build_info['cmd'],
                                                 build_info['name'],
                                                 build_info['status'],
                                                 build_info['output'])

                # when a running step is sent it means that the step
                # has just started
                if step.status == 'running':
                    msg = 'Executing command {} for {}'.format(
                        step.command, repository.url)

                    self.log(msg)
                    step.started = datetime.datetime.now()
                    yield from to_asyncio_future(build.save())
                    step_started.send(self, build=build, step=step)

                # here the step was finished
                else:
                    msg = 'Command {} for {} finished with output {}'.format(
                        step.command,  repository.url, step.output)

                    self.log(msg)
                    # same time stuff shit
                    step.finished = datetime.datetime.now()
                    step_finished.send(self, build=build, step=step)

        build.status = build_info['status']
        build.finished = datetime.datetime.now()
        # again the asyncio Future vs tornado Future
        yield from to_asyncio_future(build.save())
        build_finished.send(self, build)
        return build

    def log(self, msg):
        basemsg = '[slave {} - {}] '.format((self.host, self.port),
                                            datetime.datetime.now())
        msg = basemsg + msg
        log(msg)

    @asyncio.coroutine
    def _get_step(self, build, cmd, name, status, output):
        requested_step = None
        for step in build.steps:
            if step.command == cmd:
                step.status = status
                step.output = output
                requested_step = step

        if not requested_step:
            requested_step = BuildStep(name=name, command=cmd,
                                       status=status, output=output)
            build.steps.append(requested_step)

        yield from to_asyncio_future(build.save())
        return requested_step


class BuildManager:

    """ Controls which builds should be executed sequentially or
    in parallel.
    """

    def __init__(self, repository):
        self.repository = repository
        # each slave has its own queue
        self._queues = defaultdict(deque)

        # to keep track of which slave is already working
        # on consume its queue
        self._is_working = defaultdict(lambda: False)

        self.connect2signals()

    @asyncio.coroutine
    def add_builds(self, revision):
        """ Adds the builds for a given revision in the build queue. """

        for slave in self.repository.slaves:
            builders = yield from self.get_builders(slave, revision)
            for builder in builders:
                yield from self.add_build(builder, revision.branch,
                                          revision.commit, slave)

    @asyncio.coroutine
    def add_build(self, builder, branch, named_tree, slave):
        build = Build(repository=self.repository, branch=branch,
                      named_tree=named_tree, slave=slave,
                      builder=builder)

        yield from to_asyncio_future(build.save())
        self._queues[slave].append(build)
        if not self._is_working[slave]:
            asyncio.async(self._execute_builds(slave))

    @asyncio.coroutine
    def get_builders(self, slave, revision):
        """ Get builders for a given revision. """

        repository = yield from to_asyncio_future(revision.repository)
        builders = yield from slave.list_builders(revision)
        blist = []
        for builder_name in builders:
            try:
                builder = yield from to_asyncio_future(
                    Builder.objects.get(name=builder_name,
                                        repository=repository))
            except Builder.DoesNotExist:
                builder = Builder(name=builder_name, repository=repository)
                yield from to_asyncio_future(builder.save())

            blist.append(builder)

        return blist

    def connect2signals(self):

        @asyncio.coroutine
        def revadded(sender, revision):  # pragma no cover
            yield from self.add_builds(revision)

        revision_added.connect(revadded, sender=self.repository)

    @asyncio.coroutine
    def _execute_builds(self, slave):
        """ Execute the builds in the queue of a given slave. """

        self._is_working[slave] = True
        try:
            while True:
                try:
                    build = self._queues[slave].popleft()
                    # the build could be executed in parallel with some
                    # other preceding build
                    while build.status != build.PENDING:
                        build = self._queues[slave].popleft()
                except IndexError:
                    break

                parallels = [build] + (yield from build.get_parallels())
                yield from self._execute_in_parallel(slave, parallels)
        finally:
            self._is_working[slave] = False

    @asyncio.coroutine
    def _execute_in_parallel(self, slave, builds):
        fs = []
        for build in builds:
            f = asyncio.async(slave.build(build))
            fs.append(f)

        yield from asyncio.wait(fs)
        return fs


# This first signal is sent by a vcs when a new revision is detected.
revision_added.connect(BuildManager.add_builds)
