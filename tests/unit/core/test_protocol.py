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
import json
from unittest import mock, TestCase
from toxicbuild.core import protocol
from tests import async_test


class BaseToxicProtocolTest(TestCase):

    def setUp(self):
        super().setUp()
        loop = mock.Mock()
        self.protocol = protocol.BaseToxicProtocol(loop)
        self.protocol._stream_reader = mock.MagicMock()
        self.protocol._stream_writer = mock.MagicMock()
        self.protocol.salt = protocol.utils.bcrypt.gensalt(4)
        self.protocol.encrypted_token = protocol.utils.bcrypt_string(
            '123sd', self.protocol.salt)

        self.response = None

        def w(msg):
            data = ''
            for i, ordin in enumerate(msg):
                char = chr(ordin)
                if char == '\n':
                    break
                data += char

            y = i + 1
            full_data = msg[y:y + int(data)]

            self.response = json.loads(full_data.decode())

        self.protocol._stream_writer.write = w

        # the return of _stream_reader.read()
        self.message = json.dumps(
            {'action': 'thing', 'token': '123sd'}).encode('utf-8')

        self.full_message = '{}\n'.format(len(self.message)).encode(
            'utf-8') + self.message

        self._rlimit = 0

        @asyncio.coroutine
        def r(limit):
            part = self.full_message[self._rlimit:limit + self._rlimit]
            self._rlimit += limit
            return part

        self.protocol._stream_reader.read = r

    def test_call(self):

        self.assertEqual(self.protocol(), self.protocol)

    @mock.patch.object(protocol.asyncio, 'StreamReader', mock.Mock())
    @mock.patch.object(protocol.asyncio, 'StreamWriter', mock.MagicMock())
    @async_test
    def test_connection_made(self):
        # what it does is to ensure that the client_connected method,
        # that is the callback called when a connection is made, is
        # calle correctly
        loop = mock.Mock()
        prot = protocol.BaseToxicProtocol(loop)
        prot._stream_reader = mock.MagicMock()
        prot._stream_writer = mock.MagicMock()
        prot._stream_reader.read = self.protocol._stream_reader.read
        transport = mock.Mock()
        cc_mock = mock.Mock()

        @asyncio.coroutine
        def cc():
            cc_mock()

        prot.client_connected = cc
        prot.salt = self.protocol.salt
        prot.encrypted_token = self.protocol.encrypted_token
        prot.connection_made(transport)
        yield from prot._check_data_future
        yield from prot._client_connected_future
        self.assertTrue(cc_mock.called)

    @mock.patch.object(protocol.asyncio, 'StreamWriter', mock.MagicMock())
    def test_connection_lost(self):
        self.protocol.connection_lost(mock.Mock())
        self.assertTrue(self.protocol._stream_writer.close.called)

    @mock.patch.object(protocol.asyncio, 'StreamWriter', mock.MagicMock())
    def test_connection_lost_with_cb(self):
        self.protocol.connection_lost_cb = mock.Mock()
        self.protocol.connection_lost(mock.Mock())
        self.assertTrue(self.protocol._stream_writer.close.called)
        self.assertTrue(self.protocol.connection_lost_cb.called)

    @mock.patch.object(protocol.utils, 'log', mock.Mock())
    @async_test
    def test_check_data_without_data(self):
        self.full_message = b''

        yield from self.protocol.check_data()

        self.assertEqual(self.response['code'], 1)

    @mock.patch.object(protocol.utils, 'log', mock.Mock())
    @async_test
    def test_check_data_without_token(self):
        message = '{"salci": "fufu"}'
        self.full_message = '{}\n'.format(len(message)) + message
        self.full_message = self.full_message.encode('utf-8')

        yield from self.protocol.check_data()
        self.assertEqual(self.response['code'], 2)

    @mock.patch.object(protocol.utils, 'log', mock.Mock())
    @async_test
    def test_check_data_with_bad_token(self):
        message = '{"salci": "fufu", "token": "123sdf"}'
        self.protocol.salt = protocol.utils.bcrypt.gensalt(4)
        self.protocol.encrypted_token = protocol.utils.bcrypt_string(
            '123sd', self.protocol.salt)
        self.full_message = '{}\n'.format(len(message)) + message
        self.full_message = self.full_message.encode('utf-8')

        yield from self.protocol.check_data()
        self.assertEqual(self.response['code'], 3)

    @async_test
    def test_check_data_without_action(self):
        message = '{"salci": "fufu", "token": "123sd"}'
        self.full_message = '{}\n'.format(len(message)) + message
        self.full_message = self.full_message.encode('utf-8')

        yield from self.protocol.check_data()
        self.assertEqual(self.response['code'], 1)

    @async_test
    def test_check_data(self):
        message = '{"action": "hack!", "token": "123sd"}'
        self.full_message = '{}\n'.format(len(message)) + message
        self.full_message = self.full_message.encode('utf-8')

        yield from self.protocol.check_data()

        self.assertEqual(self.protocol.action, 'hack!')

    @async_test
    def test_send_response(self):
        expected = {'code': 0,
                    'body': 'something!'}

        yield from self.protocol.send_response(code=0, body='something!')

        self.assertEqual(expected, self.response)

    @async_test
    def test_get_raw_data(self):
        raw = yield from self.protocol.get_raw_data()
        self.assertEqual(raw, self.message)

    @async_test
    def test_get_json_data(self):
        json_data = yield from self.protocol.get_json_data()

        self.assertEqual(json_data, json.loads(self.message.decode()))

    def test_close_connection(self):
        self.protocol.close_connection()

        self.assertTrue(self.protocol._stream_writer.close.called)
