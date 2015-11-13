import asyncio
from aiohttp import web
import jsonrpclib
from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCDispatcher
import sys

class AsyncMultipathJSONRPCServer(SimpleJSONRPCDispatcher):
    def __init__(self, loop = None, **kwargs):
        if loop is None:
            loop = asyncio.get_event_loop()
        SimpleJSONRPCDispatcher.__init__(self, **kwargs)
        self._loop = loop
        self._app = web.Application(loop = loop)
        self._app.router.add_route('POST', '/', self._dispatchFunction)
        self._app.router.add_route('POST', '/{path}', self._dispatchToInstance)
        self._dispatchers = {}

    @asyncio.coroutine
    def _dispatchFunction(self, request):
        data = yield from request.text()
        response = self._marshaled_dispatch(data, None, '/')
        return web.Response(text = response,
                            content_type = self.json_config.content_type)

    @asyncio.coroutine
    def _dispatchToInstance(self, request):
        path = request.match_info.get('path')
        try:
            response = self._dispatchers[path]._marshaled_dispatch(
               (yield from request.text()), None, path)
        except:
            # report low level exception back to server
            # (each dispatcher should have handled their own
            # exceptions)
            exc_type, exc_value = sys.exc_info()[:2]
            response = jsonrpclib.jdumps(
                jsonrpclib.Fault(1, "%s:%s" % (exc_type, exc_value)),
                encoding=self.encoding)
            response = response.encode(self.encoding)
        return web.Response(text = response,
                            content_type = self.json_config.content_type)

    def register_instance(self, instance, path, **kwargs):
        dispatcher = SimpleJSONRPCDispatcher(**kwargs)
        dispatcher.register_instance(instance)
        self._dispatchers[path] = dispatcher

    @asyncio.coroutine
    def create_server(self, address, port):
        srv = yield from self._loop.create_server(self._app.make_handler(),
                                                  address, port)
        return srv
