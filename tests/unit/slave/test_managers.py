# -*- coding: utf-8 -*-

# Copyright 2015-2016 Juca Crispim <juca@poraodojuca.net>

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
import os
from unittest import TestCase
from unittest.mock import patch, MagicMock, Mock
import tornado
from toxicbuild.core.utils import load_module_from_file
from toxicbuild.slave import plugins, managers
from tests.unit.slave import TEST_DATA_DIR
from tests import async_test

TOXICCONF = os.path.join(TEST_DATA_DIR, 'toxicbuild.conf')
TOXICCONF = load_module_from_file(TOXICCONF)

BADTOXICCONF = os.path.join(TEST_DATA_DIR, 'badtoxicbuild.conf')
BADTOXICCONF = load_module_from_file(BADTOXICCONF)


@patch.object(managers, 'get_toxicbuildconf',
              Mock(return_value=TOXICCONF))
class BuilderManagerTest(TestCase):

    @patch.object(managers, 'get_vcs', MagicMock())
    def setUp(self):
        super().setUp()
        protocol = MagicMock()

        @asyncio.coroutine
        def s(*a, **kw):
            pass

        protocol.send_response = s

        self.manager = managers.BuildManager(protocol, 'git@repo.git', 'git',
                                             'master', 'v0.1')

    def tearDown(self):
        managers.BuildManager.cloning_repos = set()
        managers.BuildManager.updating_repos = set()

    def get_new_ioloop(self):
        return tornado.ioloop.IOLoop.instance()

    def test_is_cloning_without_clone(self):
        manager = managers.BuildManager(MagicMock(), 'git@repo.git', 'git',
                                        'master', 'v0.1')

        manager.is_cloning = False

        self.assertFalse(self.manager.is_cloning)

    def test_is_cloning(self):
        try:
            manager = managers.BuildManager(MagicMock(), 'git@repo.git', 'git',
                                            'master', 'v0.1')

            manager.is_cloning = True

            self.assertTrue(self.manager.is_cloning)

        finally:
            managers.BuildManager.cloning_repos = set()

    def test_is_updating_without_update(self):
        manager = managers.BuildManager(MagicMock(), 'git@repo.git', 'git',
                                        'master', 'v0.1')

        manager.is_updating = False

        self.assertFalse(self.manager.is_updating)

    def test_is_updating(self):
        manager = managers.BuildManager(MagicMock(), 'git@repo.git', 'git',
                                        'master', 'v0.1')

        manager.is_updating = True

        self.assertTrue(self.manager.is_updating)

    def test_is_working_with_clone(self):
        manager = managers.BuildManager(MagicMock(), 'git@repo.git', 'git',
                                        'master', 'v0.1')

        manager.is_cloning = True

        self.assertTrue(self.manager.is_working)

    def test_is_working_with_update(self):
        manager = managers.BuildManager(MagicMock(), 'git@repo.git', 'git',
                                        'master', 'v0.1')

        manager.is_updating = True

        self.assertTrue(self.manager.is_working)

    def test_is_working_not_working(self):
        manager = managers.BuildManager(MagicMock(), 'git@repo.git', 'git',
                                        'master', 'v0.1')

        manager.is_updating = False
        manager.is_cloning = False

        self.assertFalse(self.manager.is_working)

    def test_current_build(self):
        manager = managers.BuildManager(MagicMock(), 'git@repo.git', 'git',
                                        'master', 'v0.1')
        try:
            manager.current_build = 'v0.1'
            self.assertEqual(
                managers.BuildManager.building_repos[manager.repo_url], 'v0.1')
            self.assertTrue(manager.current_build)
        finally:
            manager.current_build = None

    def test_current_build_without_build(self):
        manager = managers.BuildManager(MagicMock(), 'git@repo.git', 'git',
                                        'master', 'v0.1')
        self.assertIsNone(manager.current_build)

    def test_enter_with_other_current_build(self):
        manager = managers.BuildManager(MagicMock(), 'git@repo.git', 'git',
                                        'master', 'v0.1')
        manager.current_build = 'v0.1.1'
        with self.assertRaises(managers.BusyRepository):
            with manager as m:
                del m

    def test_enter_with_same_current_build(self):
        manager = managers.BuildManager(MagicMock(), 'git@repo.git', 'git',
                                        'master', 'v0.1')
        manager.current_build = 'v0.1'
        with manager as m:
            self.assertEqual(m.current_build, 'v0.1')

    def test_enter_without_current_build(self):
        manager = managers.BuildManager(MagicMock(), 'git@repo.git', 'git',
                                        'master', 'v0.1')
        with manager as m:
            self.assertEqual(m.current_build, 'v0.1')

    @async_test
    def test_wait_clone(self):
        class TBM(managers.BuildManager):
            clone_called = False
            call_count = -1

            @property
            def is_cloning(self):
                self.clone_called = True
                self.call_count += 1
                return [True, False][self.call_count]

        manager = TBM(MagicMock(), 'git@repo.git', 'git', 'master', 'v0.1')
        yield from manager.wait_clone()

        self.assertTrue(manager.clone_called)

    @async_test
    def test_wait_update(self):
        class TBM(managers.BuildManager):
            update_called = False
            call_count = -1

            @property
            def is_updating(self):
                self.update_called = True
                self.call_count += 1
                return [True, False][self.call_count]

        manager = TBM(MagicMock(), 'git@repo.git', 'git', 'master', 'v0.1')
        yield from manager.wait_update()

        self.assertTrue(manager.update_called)

    @async_test
    def test_wait_all(self):
        class TBM(managers.BuildManager):
            working_called = False
            call_count = -1

            @property
            def is_working(self):
                self.working_called = True
                self.call_count += 1
                return [True, False][self.call_count]

        manager = TBM(MagicMock(), 'git@repo.git', 'git', 'master', 'v0.1')
        yield from manager.wait_all()

        self.assertTrue(manager.working_called)

    @async_test
    def test_update_and_checkout_with_clone(self):
        self.manager.vcs.workdir_exists.return_value = False
        self.manager.vcs.checkout = MagicMock()
        yield from self.manager.update_and_checkout()

        self.assertTrue(self.manager.vcs.clone.called)
        self.assertTrue(self.manager.vcs.checkout.called)

    @patch.object(managers.BuildManager, 'is_working', MagicMock())
    @patch.object(managers.BuildManager, 'wait_all', MagicMock())
    @async_test
    def test_update_and_checkout_working(self):
        yield from self.manager.update_and_checkout()

        self.assertTrue(self.manager.wait_all.called)

    @async_test
    def test_update_and_checkout_without_clone(self):
        self.manager.vcs.clone = MagicMock()
        self.manager.vcs.checkout = MagicMock()
        self.manager.vcs.workdir_exists.return_value = True

        yield from self.manager.update_and_checkout()

        self.assertFalse(self.manager.vcs.clone.called)
        self.assertTrue(self.manager.vcs.checkout.called)

    @patch.object(managers.BuildManager, 'is_working', MagicMock())
    @patch.object(managers.BuildManager, 'wait_all', MagicMock())
    @async_test
    def test_update_and_checkout_working_not_wait(self):
        self.manager.vcs.checkout = Mock()
        yield from self.manager.update_and_checkout(work_after_wait=False)

        self.assertTrue(self.manager.wait_all.called)
        self.assertFalse(self.manager.vcs.checkout.called)

    @patch.object(managers.BuildManager, 'is_working', MagicMock())
    @patch.object(managers.BuildManager, 'wait_all', MagicMock())
    @async_test
    def test_update_and_checkout_new_named_tree(self):
        self.manager.vcs.checkout = MagicMock(side_effect=[
            managers.ExecCmdError, MagicMock(), MagicMock()])
        yield from self.manager.update_and_checkout()

        self.assertEqual(len(self.manager.vcs.checkout.call_args_list), 3)

    @patch.object(managers.BuildManager, 'is_working', MagicMock())
    @patch.object(managers.BuildManager, 'wait_all', MagicMock())
    @async_test
    def test_update_and_checkout_known_named_tree(self):
        self.manager.vcs.checkout = MagicMock()
        yield from self.manager.update_and_checkout()

        self.assertEqual(len(self.manager.vcs.checkout.call_args_list), 1)

    def test_list_builders(self):
        expected = ['builder1', 'builder2', 'builder3', 'builder4']
        returned = self.manager.list_builders()

        self.assertEqual(returned, expected)

    def test_list_builders_with_bad_builder_config(self):
        self.manager._configmodule = BADTOXICCONF
        with self.assertRaises(managers.BadBuilderConfig):
            self.manager.list_builders()

    def test_load_builder(self):
        builder = self.manager.load_builder('builder1')
        self.assertEqual(len(builder.steps), 2)

    def test_load_builder_with_plugin(self):
        builder = self.manager.load_builder('builder3')
        self.assertEqual(len(builder.steps), 3)

    def test_load_builder_with_not_found(self):
        with self.assertRaises(managers.BuilderNotFound):
            builder = self.manager.load_builder('builder300')
            del builder

    def test_load_builder_with_envvars(self):
        builder = self.manager.load_builder('builder4')
        self.assertTrue(builder.envvars)

    def test_load_plugins(self):
        plugins_conf = [{'name': 'python-venv',
                         'pyversion': '/usr/bin/python3.4'}]
        returned = self.manager._load_plugins(plugins_conf)

        self.assertEqual(type(returned[0]), plugins.PythonVenvPlugin)
