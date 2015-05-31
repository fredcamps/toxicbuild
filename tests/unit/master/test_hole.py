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
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch
import tornado
from tornado.testing import AsyncTestCase, gen_test
from toxicbuild.master import hole, build, repositories


class UIHoleTest(AsyncTestCase):

    @patch.object(hole.HoleHandler, 'handle', MagicMock())
    @patch.object(hole.BaseToxicProtocol, 'send_response', MagicMock())
    @gen_test
    def test_client_connected_ok(self):
        uihole = hole.UIHole(Mock())
        uihole.data = {}
        uihole._stream_writer = Mock()
        # no exception means ok
        yield from uihole.client_connected()

    @patch.object(hole, 'UIStreamHandler', Mock())
    @patch.object(hole.BaseToxicProtocol, 'send_response', MagicMock())
    @gen_test
    def test_client_connected_with_stream(self):
        uihole = hole.UIHole(Mock())
        uihole.data = {}
        uihole.action = 'stream'
        uihole._stream_writer = Mock()

        yield from uihole.client_connected()

        self.assertTrue(hole.UIStreamHandler.called)

    @patch.object(hole.HoleHandler, 'handle', MagicMock())
    @patch.object(hole.BaseToxicProtocol, 'send_response', MagicMock())
    @gen_test
    def test_client_connected_error(self):

        @asyncio.coroutine
        def handle(*a, **kw):
            raise Exception('bla')

        hole.HoleHandler.handle = handle
        uihole = hole.UIHole(Mock())
        uihole.data = {}
        uihole._stream_writer = Mock()

        yield from uihole.client_connected()

        response = uihole.send_response.call_args[1]
        response_code = response['code']
        self.assertEqual(response_code, 1, response)


@patch.object(hole, 'log', Mock())
@patch.object(repositories.utils, 'log', Mock())
class HoleHandlerTest(AsyncTestCase):

    def tearDown(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(asyncio.gather(*asyncio.Task.all_tasks()))
        hole.Slave.drop_collection()
        hole.Repository.drop_collection()
        build.Builder.drop_collection()
        build.Build.drop_collection()
        super().tearDown()

    def get_new_ioloop(self):
        return tornado.ioloop.IOLoop.instance()

    @gen_test
    def test_handle(self):
        protocol = MagicMock()
        handler = hole.HoleHandler({}, 'my-action', protocol)
        handler.my_action = lambda *a, **kw: None

        yield from handler.handle()
        code = protocol.send_response.call_args[1]['code']

        self.assertEqual(code, 0)

    @gen_test
    def test_handle_with_coro(self):
        protocol = MagicMock()
        handler = hole.HoleHandler({}, 'my-action', protocol)

        @asyncio.coroutine
        def my_action(*a, ** kw):
            return True

        handler.my_action = my_action

        yield from handler.handle()
        code = protocol.send_response.call_args[1]['code']

        self.assertEqual(code, 0)

    @gen_test
    def test_handle_with_not_known_action(self):
        handler = hole.HoleHandler({}, 'action', MagicMock())

        with self.assertRaises(hole.UIFunctionNotFound):
            yield from handler.handle()

    @patch.object(repositories.Repository, 'first_run', MagicMock())
    @gen_test
    def test_repo_add(self):
        yield from self._create_test_data()

        name = 'reponameoutro'
        url = 'git@somehere.com'
        vcs_type = 'git'
        update_seconds = 300
        slaves = ['name']
        action = 'repo-add'
        handler = hole.HoleHandler({}, action, MagicMock())

        repo = yield from handler.repo_add(name, url, update_seconds, vcs_type,
                                           slaves)

        self.assertTrue(repo['repo-add']['_id'])

    @patch.object(repositories, 'shutil', Mock())
    @patch.object(repositories.Repository, 'first_run', MagicMock())
    @gen_test
    def test_repo_remove(self):
        yield from self._create_test_data()
        action = 'repo-remove'
        handler = hole.HoleHandler({}, action, MagicMock())
        yield from handler.repo_remove(repo_name='reponame')

        self.assertEqual((yield hole.Repository.objects.count()), 0)

    @patch.object(repositories.Repository, 'first_run', MagicMock())
    @gen_test
    def test_repo_list(self):
        yield from self._create_test_data()
        handler = hole.HoleHandler({}, 'repo-list', MagicMock())
        repo_list = (yield from handler.repo_list())['repo-list']

        self.assertEqual(len(repo_list), 1)

    @patch.object(repositories.Repository, 'first_run', MagicMock())
    @gen_test
    def test_repo_update(self):
        yield from self._create_test_data()

        data = {'url': 'git@somewhere.com',
                'update_seconds': 60}
        action = 'repo-update'
        handler = hole.HoleHandler(data, action, MagicMock())
        yield from handler.repo_update(repo_name=self.repo.name,
                                       update_seconds=60)
        repo = yield from hole.Repository.get(name=self.repo.name)

        self.assertEqual(repo.update_seconds, 60)

    @patch.object(repositories.Repository, 'first_run', MagicMock())
    @gen_test
    def test_repo_add_slave(self):
        yield from self._create_test_data()

        slave = yield from hole.Slave.create(name='name2',
                                             host='127.0.0.1', port=1234)

        repo_name = self.repo.name
        action = 'repo-add-slave'

        handler = hole.HoleHandler({}, action, MagicMock())

        yield from handler.repo_add_slave(repo_name=repo_name,
                                          slave_name='name2')

        repo = yield from hole.Repository.get(url=self.repo.url)

        self.assertEqual(repo.slaves[0].id, slave.id)

    @patch.object(repositories.Repository, 'first_run', MagicMock())
    @gen_test
    def test_repo_remove_slave(self):
        yield from self._create_test_data()

        slave = yield from hole.Slave.create(name='name2', host='127.0.0.1',
                                             port=1234)
        yield from self.repo.add_slave(slave)

        handler = hole.HoleHandler({}, 'repo-remove-slave', MagicMock())

        yield from handler.repo_remove_slave(self.repo.name, slave.name)

        repo = yield from hole.Repository.get(url=self.repo.url)

        self.assertEqual(len(repo.slaves), 0)

    @patch.object(hole.Slave, 'list_builders', MagicMock())
    @patch.object(hole.Repository, 'add_build', MagicMock())
    @patch.object(repositories.Repository, 'first_run', MagicMock())
    @gen_test
    def test_repo_start_build(self):
        yield from self._create_test_data()

        hole.Slave.list_builders = asyncio.coroutine(lambda s, r: [Mock()])
        handler = hole.HoleHandler({}, 'repo-start-build', MagicMock())
        self.repo.slaves = [self.slave]
        yield self.repo.save()

        yield from handler.repo_start_build(self.repo.name, 'master')

        self.assertEqual(len(self.repo.add_build.call_args_list), 1)

    @patch.object(hole.Slave, 'list_builders', MagicMock())
    @patch.object(hole.Repository, 'add_build', MagicMock())
    @patch.object(repositories.Repository, 'first_run', MagicMock())
    @gen_test
    def test_repo_start_build_with_builder_name(self):
        yield from self._create_test_data()

        hole.Slave.list_builders = asyncio.coroutine(lambda s, r: [Mock()])
        handler = hole.HoleHandler({}, 'repo-start-build', MagicMock())
        self.repo.slaves = [self.slave]
        yield self.repo.save()

        yield from handler.repo_start_build(self.repo.name, 'master',
                                            builder_name='b0')

        self.assertEqual(len(self.repo.add_build.call_args_list), 1)

    @patch.object(hole.Slave, 'list_builders', MagicMock())
    @patch.object(hole.Repository, 'add_build', MagicMock())
    @patch.object(repositories.Repository, 'first_run', MagicMock())
    @gen_test
    def test_repo_start_build_with_named_tree(self):
        yield from self._create_test_data()

        hole.Slave.list_builders = asyncio.coroutine(lambda s, r: [Mock()])
        handler = hole.HoleHandler({}, 'repo-start-build', MagicMock())
        self.repo.slaves = [self.slave]
        yield self.repo.save()

        yield from handler.repo_start_build(self.repo.name, 'master',
                                            named_tree='123qewad')

        self.assertEqual(len(self.repo.add_build.call_args_list), 1)

    @patch.object(hole.Slave, 'list_builders', MagicMock())
    @patch.object(hole.Repository, 'add_build', MagicMock())
    @patch.object(repositories.Repository, 'first_run', MagicMock())
    @gen_test
    def test_repo_start_build_with_slave(self):
        yield from self._create_test_data()

        hole.Slave.list_builders = asyncio.coroutine(lambda s, r: [Mock()])
        handler = hole.HoleHandler({}, 'repo-start-build', MagicMock())
        self.repo.slaves = [self.slave]
        yield self.repo.save()

        yield from handler.repo_start_build(self.repo.name, 'master',
                                            slaves=['name'])

        self.assertEqual(len(self.repo.add_build.call_args_list), 1)

    @gen_test
    def test_slave_add(self):
        data = {'host': '127.0.0.1', 'port': 1234}
        handler = hole.HoleHandler(data, 'slave-add', MagicMock())
        slave = yield from handler.slave_add(slave_name='slave',
                                             slave_host='locahost',
                                             slave_port=1234)
        slave = slave['slave-add']

        self.assertTrue(slave['_id'])

    @patch.object(repositories.Repository, 'first_run', MagicMock())
    @gen_test
    def test_slave_remove(self):
        yield from self._create_test_data()
        data = {'host': '127.0.0.1', 'port': 7777}
        handler = hole.HoleHandler(data, 'slave-remove', MagicMock())
        yield from handler.slave_remove(slave_name='name')

        self.assertEqual((yield hole.Slave.objects.count()), 0)

    @patch.object(repositories.Repository, 'first_run', MagicMock())
    @gen_test
    def test_slave_list(self):
        yield from self._create_test_data()
        handler = hole.HoleHandler({}, 'slave-list', MagicMock())
        slaves = (yield from handler.slave_list())['slave-list']

        self.assertEqual(len(slaves), 1)

    @patch.object(repositories.Repository, 'first_run', MagicMock())
    @gen_test
    def test_builder_list(self):

        yield from self._create_test_data()
        handler = hole.HoleHandler({}, 'builder-list', MagicMock())

        builders = yield from handler.builder_list(self.repo.name)
        builders = builders['builder-list']
        self.assertEqual(len(builders), 3)

    @patch.object(repositories.Repository, 'first_run', MagicMock())
    @gen_test
    def test_builder_show(self):
        yield from self._create_test_data()

        data = {'name': 'b0', 'repo-url': self.repo.url}
        action = 'builder-show'
        handler = hole.HoleHandler(data, action, MagicMock())
        builder = yield from handler.builder_show(repo_name=self.repo.name,
                                                  builder_name='b0')
        builder = builder['builder-show']

        self.assertEqual(len(builder['builds']), 1)

    def test_get_method_signature(self):

        def target(a, b='bla', c=None):
            pass

        expected = {'doc': '',
                    'parameters': [{'name': 'a', 'required': True},
                                   {'name': 'b', 'required': False,
                                    'default': 'bla'},
                                   {'name': 'c', 'required': False,
                                    'default': None}]}

        handler = hole.HoleHandler({}, 'action', MagicMock())
        returned = handler._get_method_signature(target)

        self.assertEqual(returned, expected, returned)

    @patch.object(repositories.Repository, 'first_run', MagicMock())
    @patch.object(hole.Slave, 'list_builders', MagicMock())
    @gen_test
    def test_get_builders(self):
        yield from self._create_test_data()
        hole.Slave.list_builders = asyncio.coroutine(
            lambda s, r: [self.builders[0]])
        slaves = [self.slave]
        expected = {self.slave: [self.builders[0]]}
        handler = hole.HoleHandler({}, 'action', self)

        builders = yield from handler._get_builders(slaves, self.revision)

        self.assertEqual(builders, expected)

    def test_list_funcs(self):
        handler = hole.HoleHandler({}, 'action', MagicMock())
        funcs = handler.list_funcs()['list-funcs']

        keys = sorted([k.replace('_', '-') for k
                       in handler._get_action_methods().keys()])
        funcs = sorted(list(funcs.keys()))
        self.assertEqual(funcs, keys)

    @patch.object(repositories.utils, 'log', Mock())
    @asyncio.coroutine
    def _create_test_data(self):

        self.slave = hole.Slave(name='name', host='127.0.0.1', port=7777)
        yield self.slave.save()
        self.repo = yield from hole.Repository.create(
            'reponame', 'git@somewhere.com', 300, 'git')

        self.builds = []
        now = datetime.now()
        self.revision = repositories.RepositoryRevision(repository=self.repo,
                                                        commit='123qewad',
                                                        branch='master',
                                                        commit_date=now)
        yield self.revision.save()
        self.builders = []
        for i in range(3):
            builder = build.Builder(name='b{}'.format(i), repository=self.repo)
            yield builder.save()
            build_inst = hole.Build(repository=self.repo, slave=self.slave,
                                    branch='master', named_tree='v0.{}'.format(i),
                                    started=datetime.now(),
                                    finished=datetime.now(),
                                    builder=builder, status='success')
            yield build_inst.save()
            self.builders.append(build_inst)


class UIStreamHandlerTest(AsyncTestCase):

    def setUp(self):
        super().setUp()
        protocol = MagicMock()
        self.handler = hole.UIStreamHandler(protocol)

    def get_new_ioloop(self):
        return tornado.ioloop.IOLoop.instance()

    def tearDown(self):
        build.Build.drop_collection()
        build.Builder.drop_collection()
        build.Slave.drop_collection()
        repositories.Repository.drop_collection()

    @patch.object(hole, 'step_started', Mock())
    @patch.object(hole, 'step_finished', Mock())
    @patch.object(hole, 'build_started', Mock())
    @patch.object(hole, 'build_finished', Mock())
    def test_connect2signals(self):

        self.handler._connect2signals()
        self.assertTrue(all([hole.step_started.connect.called,
                             hole.step_finished.connect.called,
                             hole.build_started.connect.called,
                             hole.build_finished.connect.called]))

    def test_getattr(self):
        self.assertTrue(self.handler.step_started())

    @patch.object(repositories.Repository, 'schedule', Mock())
    @patch.object(hole.BaseToxicProtocol, 'send_response', Mock())
    @patch.object(repositories.Repository, 'first_run', MagicMock())
    @gen_test
    def test_send_info_step(self):
        testrepo = yield from repositories.Repository.create('name',
                                                             'git@git.nada',
                                                             300, 'git')
        testslave = yield from build.Slave.create(name='name',
                                                  host='localhost',
                                                  port=1234)

        testbuilder = yield from build.Builder.create(name='b1',
                                                      repository=testrepo)
        testbuild = build.Build(repository=testrepo, slave=testslave,
                                branch='master', named_tree='master',
                                builder=testbuilder, status='running')
        yield testbuild.save()

        teststep = build.BuildStep(name='s1', command='ls', status='running',
                                   output='')
        testbuild.steps.append(teststep)
        yield testbuild.save()

        self.CODE = None
        self.BODY = None

        @asyncio.coroutine
        def sr(code, body):
            self.CODE = code
            self.BODY = body

        self.handler.protocol.send_response = sr

        f = yield from self.handler.send_info('step-started',
                                              build=testbuild, step=teststep)
        yield from f

        self.assertEqual(self.CODE, 0)
        self.assertIn('build', self.BODY.keys())

    @patch.object(repositories.Repository, 'schedule', Mock())
    @patch.object(hole.BaseToxicProtocol, 'send_response', Mock())
    @patch.object(repositories.Repository, 'first_run', MagicMock())
    @gen_test
    def test_send_info_build(self):
        testrepo = yield from repositories.Repository.create('name',
                                                             'git@git.nada',
                                                             300, 'git')
        testslave = yield from build.Slave.create(name='name',
                                                  host='localhost',
                                                  port=1234)
        testbuilder = yield from build.Builder.create(name='b1',
                                                      repository=testrepo)
        testbuild = build.Build(repository=testrepo, slave=testslave,
                                branch='master', named_tree='master',
                                builder=testbuilder, status='running')
        yield testbuild.save()

        self.CODE = None
        self.BODY = None

        @asyncio.coroutine
        def sr(code, body):
            self.CODE = code
            self.BODY = body

        self.handler.protocol.send_response = sr

        f = yield from self.handler.send_info('step-started', build=testbuild)
        yield from f

        self.assertEqual(self.CODE, 0)
        self.assertIn('steps', self.BODY.keys())


class HoleServerTest(AsyncTestCase):

    def setUp(self):
        super().setUp()
        self.server = hole.HoleServer()

    def test_get_protocol_instance(self):
        prot = self.server.get_protocol_instance()

        self.assertEqual(hole.UIHole, type(prot))

    @patch.object(hole.asyncio, 'get_event_loop', Mock())
    @patch.object(hole.asyncio, 'async', Mock())
    def test_serve(self):
        self.server.serve()

        self.assertTrue(hole.asyncio.async.called)