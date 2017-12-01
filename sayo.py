__author__ = 'Samuel Charron'
__version__ = '0.1.dev0'
__license__ = 'MIT'

import asyncio
import json
import logging
import ssl

import websockets

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('websockets')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

logger = logging.getLogger('SocketIO')
logger.setLevel(logging.DEBUG)


class Sayo:
    def __init__(self, loop):
        self.loop: asyncio.BaseEventLoop = loop
        self.conn: websockets.client.WebSocketClientProtocol = None
        self.sid = None
        self.timeout = 5000
        self.ping_interval = 1000
        self.callbacks = {}
        self.sequence = 0
        self.logger = logging.getLogger("SocketIO")
        self.ping = None
        self.send_queue = []
        self.receiver: asyncio.Future = None
        self.events = {}
        self._closing = False
        self._close_future = None

    async def connect(self, uri, verify=True):
        if uri.startswith("wss"):
            if verify:
                raise NotImplementedError
            else:
                ctx = ssl.SSLContext()
                ctx.verify_mode = ssl.CERT_NONE
        else:
            ctx = None

        self.conn = await websockets.connect(uri + "/socket.io/?EIO=3&transport=websocket", ssl=ctx)
        session = await self.conn.recv()
        if session[0] != '0':
            raise Exception("Error while connecting")
        session = json.loads(session[1:])
        self.sid = session["sid"]

        self.timeout = session["pingTimeout"] // 1000
        self.ping_interval = session["pingInterval"] // 1000

        self.ping = asyncio.ensure_future(self._schedule_ping())

    async def _schedule_ping(self):
        while True:
            self.logger.info("PING !")
            await self.conn.send("2")
            await asyncio.sleep(self.ping_interval)

    async def _wait(self):
        futures = [self.receiver, self.ping] + self.send_queue
        if self._close_future is not None:
            futures.append(self._close_future)

        when = asyncio.FIRST_COMPLETED
        if self._closing:
            when = asyncio.ALL_COMPLETED

        done, pending = await asyncio.wait(futures, timeout=self.timeout, return_when=when)
        return done, pending

    async def read(self):
        while True:
            if self.receiver is None:
                self.receiver = asyncio.ensure_future(self.conn.recv())

            done, pending = await self._wait()
            if self._closing and len(pending) == 0:
                self.logger.info("Closing connection, leaving read loop")
                return

            # Timeout
            if len(done) == 0:
                logging.warning("Timeout. Disconnecting.")
                await self._disconnect()
                return

            for d in done:
                self.logger.info("Task done " + str(d._coro))
            for p in pending:
                self.logger.info("Task pending " + str(p._coro))

            self.send_queue = [s for s in self.send_queue if s not in done]

            if self.ping in done:
                # We probably are closing the connection. Else it's a bug :)
                continue

            if self.receiver in done:
                self.process_message()

    def process_message(self):
        msg = self.receiver.result()
        self.receiver = None

        # Does nothing as we are looping infinitely
        if msg[0] == '3':
            self.logger.info("PONG !")
            return

        if msg[0:2] == '40':
            # Connected
            return

        # Handle answer messages
        if msg[0:2] == '43':
            end_of_id = msg.find("[")
            if end_of_id < 0:
                self.logger.warning("Can't ack, corrupted message")
                return

            id = int(msg[2:end_of_id])
            self.logger.info("Ack id %i" % id)
            cb = self.callbacks.pop(id, None)
            content = json.loads(msg[end_of_id:])
            if cb is not None:
                self.logger.info("Calling callback %s with args %s", cb.__name__, content)
                cb(*content)
            return

        # Handle event messages
        if msg[0:2] == '42':
            if msg[2] != '[':
                self.logger.warning("Unknown message format %s" % msg)
                return

            event = json.loads(msg[2:])
            if len(event) < 1:
                self.logger.warning("Msg is empty %s" % msg)
                return

            event, *args = event
            if event not in self.events:
                self.logger.warning("Unregistered event %s(%s)" % (event, args))
                return

            self.events[event](args)
            return

        self.logger.error("Unprocessed message %s" % msg)

    def send(self, *msg, callback=None):
        self.logger.info("Sending msg %s", msg)
        self.sequence += 1
        if callback is not None:
            self.callbacks[self.sequence] = callback
        self.send_queue.append(asyncio.ensure_future(self.conn.send("42%i" % self.sequence + json.dumps(msg))))

    def send_threadsafe(self, *msg, callback=None):
        def _wrap():
            self.send(*msg, callback=callback)

        self.loop.call_soon_threadsafe(_wrap)

    def register(self, event, callback):
        self.events[event] = callback

    async def _disconnect(self):
        self._closing = True
        self.ping.cancel()
        for s in self.send_queue:
            s.cancel()
        if self.receiver is not None:
            self.receiver.cancel()

        await self.conn.close()

    def close(self):
        self._close_future = asyncio.ensure_future(self._disconnect())
