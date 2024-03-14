from common import action
import asyncio
from traitlets import Unicode, observe
from common import ureg, Q_
from stages.tmcl import TMCL


class AxisAtController(TMCL):

    status_str = Unicode(read_only=True, default_value=str(TMCL.status.default_value),
                         priority=0).tag(name="Status")

    def __init__(self, port, objectName=None, loop=None):
        super().__init__(port, objectName=objectName, loop=loop)

        self.manipConvFactor = 0.00275
        self.setPreferredUnits(ureg.mm, ureg.dimensionless)
        self.set_trait('referenceable', True)  # added by CM
        self.unit = "mm"
        self.velocity = Q_(1000)

    async def _set_important_parameters(self, store=True):
        await self._set_global_param(0, 77, 0)
        importantParams = {"max_current": (6, 70), "max_speed": (4, 1500), "standbycurrent": (7, 8),
                           "max_accel": (5, 1000), "right_limit_switch_disable": (12, 0),
                           "left_limit_switch_disable": (13, 0), "microstep_resolution": (140, 7),
                           "ref_search_mode": (193, 1),
                           "ref_search_speed": (194, 1000)}
        for param in importantParams:
            pm, val = importantParams[param]
            await self._set_param(pm, val)

            if store:
                await self._store_param(pm)

    async def __aenter__(self):
        await super().__aenter__()
        await self._set_important_parameters()

        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)

    @observe("status")
    def _on_status_change(self, change):
        self.set_trait("status_str", str(change["new"].name))

    @action("Halt", priority=0)
    def stop(self):
        with self.comm_lock:
            self.comm.mst(self.axis)

        if not self._isMovingFuture.done():  # added by CM
            self._isMovingFuture.cancel()

    @action("Set Position to zero", priority=1)
    async def resetCounter(self):
        await self._set_param(1, 0)
        self.set_trait('targetValue', Q_(0, self.unit))

    @action("Home to ref. switch", priority=2)
    async def reference(self):
        await self._rfs()
        while True:
            sts = await self._rfs(cmd_type="STATUS")
            self.set_trait("status_str", "Referencing")
            if not sts:
                self.set_trait("status_str", str(self.status.name))
                break
            await asyncio.sleep(0.2)

    async def waitForTargetReached(self):
        return await self._isMovingFuture

