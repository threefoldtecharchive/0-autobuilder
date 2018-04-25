import asyncio
import redis
import websockets
import json
import os
from config import config

class AutobuilderLive():
    def __init__(self):
        self.wsclients = set()
        self.redis = redis.Redis(config['redis-host'], config['redis-port'])
        self.pubsub = self.redis.pubsub()

        self.history = {}
        self.current = {}

    #
    # Websocket
    #
    async def wsbroadcast(self, event, payload):
        if not len(self.wsclients):
            return

        for client in self.wsclients:
            if not client.open:
                continue

            await client.send(json.dumps({"event": event, "payload": payload}))

    async def handler(self, websocket, path):
        self.wsclients.add(websocket)

        print("[+] websocket: new client connected")

        try:
            # pushing current data
            await websocket.send(json.dumps({"event": "history", "payload": self.history}))
            await websocket.send(json.dumps({"event": "status", "payload": self.current}))

            while True:
                if not websocket.open:
                    break

                await asyncio.sleep(1)

        finally:
            print("[+] websocket: client disconnected")
            self.wsclients.remove(websocket)

    async def fetcher(self):
        self.pubsub.subscribe(['autobuilder-current', 'autobuilder-history', 'autobuilder-update'])
        loop = asyncio.get_event_loop()

        def looper():
            for item in self.pubsub.listen():
                return item

        while True:
            print("[+] waiting for redis message")
            redis_future = loop.run_in_executor(None, looper)
            response = await redis_future

            if response['type'] != 'message':
                print("[-] received type: %s, ignoring" % response['type'])
                continue

            print(response['data'])
            channel = response['channel'].decode('utf-8')

            if channel == 'autobuilder-history':
                print("[+] history update")
                self.history = json.loads(response['data'].decode('utf-8'))
                await self.wsbroadcast("history", self.history)
                continue

            if channel == 'autobuilder-current':
                print("[+] build update")
                self.current = json.loads(response['data'].decode('utf-8'))
                await self.wsbroadcast("status", self.current)
                continue

            if channel == 'autobuilder-update':
                print("[+] specific update")
                await self.wsbroadcast("update", json.loads(response['data'].decode('utf-8')))
                continue

    def run(self):
        print("[+] initializing async")
        loop = asyncio.get_event_loop()
        loop.set_debug(True)

        print("[+] starting websocket server")
        addr = config['websocket-listen']
        port = config['websocket-port']
        websocketd = websockets.serve(self.handler, addr, port)
        asyncio.ensure_future(websocketd, loop=loop)

        print("[+] starting redis fetcher")
        asyncio.ensure_future(self.fetcher())

        print("[+] running")
        loop.run_forever()

if __name__ == '__main__':
    autobuildlive = AutobuilderLive()
    autobuildlive.run()
