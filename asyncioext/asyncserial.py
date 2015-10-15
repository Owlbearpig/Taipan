import asyncio
import asyncio.futures as futures
import serial

class Serial(serial.Serial):
    def __init__(self, loop = asyncio.get_event_loop(), *args, **kwargs):
        kwargs['timeout'] = 0
        super(serial.Serial, self).__init__(*args, **kwargs)
        self._loop = loop
        self._waiter = None
        asyncio.get_event_loop().add_reader(self.fileno(), self._readyRead)

    def _readyRead(self):
        if self._waiter != None:
            self._waiter.set_result(True)
            return

        self.readall()

    def _waitForReadyRead(self, func_name):
        if self._waiter is not None:
            raise RuntimeError('%s() called while another coroutine is '
                               'already waiting for incoming data' % func_name)

        self._waiter = futures.Future(loop=self._loop)
        try:
            yield from self._waiter
        finally:
            self._waiter = None

    @asyncio.coroutine
    def async_read(self, size=1):
        read = bytearray()
        curlen = len(read)
        while True:
            read += self.read(size - curlen)
            curlen = len(read)
            if curlen == size:
                return bytes(read)
            else:
                yield from self._waitForReadyRead('read')

    @asyncio.coroutine
    def async_readline(self, size=None, eol=b'\n'):
        """read a line which is terminated with end-of-line (eol) character
        ('\n' by default) or until timeout."""
        leneol = len(eol)
        line = bytearray()
        while True:
            c = yield from self.async_read(1)
            line += c
            if line[-leneol:] == eol:
                break
            if size is not None and len(line) >= size:
                break
        return bytes(line)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    ser = Serial(port='/dev/pts/2')

    def doSomething():
        while True:
            theLine = yield from ser.async_readline()
            print(theLine)

    asyncio.async(doSomething())
    loop.run_forever()
