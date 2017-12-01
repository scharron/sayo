from aiohttp import web
import socketio

sio = socketio.AsyncServer()
app = web.Application()
sio.attach(app)

@sio.on('ping')
async def message(sid):
    await sio.emit('pong', room=sid)

if __name__ == '__main__':
    web.run_app(app)
