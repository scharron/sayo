__author__ = 'Samuel Charron'
__version__ = '0.2.dev0'
__license__ = 'MIT'

import asyncio
import json
import logging
import ssl

import websockets

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('websockets')
logger.setLevel(logging.WARNING)
logger.addHandler(logging.StreamHandler())

logger = logging.getLogger('SocketIO')
logger.setLevel(logging.WARNING)


class Sayo:
    def __init__(self, loop):
        self.loop: asyncio.BaseEventLoop = loop
        self.conn: websockets.client.WebSocketClientProtocol = None
        self.sid = None
        self.timeout = 5000
        self.ping_interval = 1000
        self.callbacks = {}
        self.sequence = -1
        self.logger = logging.getLogger("SocketIO")
        self.ping = None
        self.send_queue = []
        self.receiver: asyncio.Future = None
        self.events = {}
        self.closing = None
        self.closing_future = None

    async def connect(self, uri):
        ctx = ssl.SSLContext()
        ctx.verify_mode = ssl.CERT_NONE
        self.conn = await websockets.connect(uri + "/socket.io/?EIO=3&transport=websocket", ssl=ctx)
        session = await self.conn.recv()
        if session[0] != '0':
            raise Exception("Error while connecting")
        session = json.loads(session[1:])
        self.sid = session["sid"]

        self.timeout = session["pingTimeout"] // 1000
        self.ping_interval = session["pingInterval"] // 1000

        self.ping = asyncio.ensure_future(self._schedule_ping())

        self.closing = asyncio.Event()
        self.closing_future = asyncio.ensure_future(self._wait_closing())

    async def _wait_closing(self):
        await self.closing.wait()

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
            # Do not interrupt
            if self.receiver is None:
                self.receiver = asyncio.ensure_future(self.conn.recv())

            futures = [self.receiver, self.ping, self.closing_future] + self.send_queue
            done, pending = await asyncio.wait(futures, timeout=self.timeout, return_when=asyncio.FIRST_COMPLETED)

            # Timeout
            if len(done) == 0:
                self._disconnect()
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

            if self.closing.is_set():
                print("closing")
                break

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

    def close(self):
        self._disconnect()

    def _disconnect(self):
        self.closing.set()
        self.conn.close()
