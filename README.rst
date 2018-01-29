==========================================================
Sayo: An incomplete socket.io client written using asyncio
==========================================================

Example
-------

.. code-block:: python

  import asyncio
  from sayo import Sayo

  loop = asyncio.new_event_loop()

  sayo = Sayo(loop)

  can_close = asyncio.Event()


  def close():
      if can_close.is_set():
          sayo.close()


  def ack():
      print("Ack")
      close()
      can_close.set()


  def pong(args):
      print("Pong", args)
      close()
      can_close.set()


  sayo.register("pong", callback=pong)


  async def run():
      await sayo.connect("ws://localhost:8080")
      sayo.send('ping', callback=ack)
      await sayo.read()


  loop.run_until_complete(
      run()
  )
