from json import dumps
from logging import getLogger
from math import isfinite
from threading import (
	Event,
	Lock,
)
from typing import (
	Optional,
	TYPE_CHECKING,
)

from ..Extension import Extension
from ..Response import Response

if TYPE_CHECKING:
	from ..Inspector import Inspector

__all__ = (
	'Ping',
)

class Ping(Extension):
	logger = getLogger('Worker.Inspector.Extensions.Ping')

	def __init__(
		self,
		path: str,
		timeout: float = 1,
	):
		super().__init__(path)
		if isinstance(
			timeout,
			bool,
		) or not isfinite(timeout) or timeout <= 0:
			raise ValueError('Ping probe timeout must be finite and positive')
		self.timeout = timeout
		self.lock = Lock()
		self.probe: Optional[Event] = None

	def state(
		self,
		inspector: 'Inspector',
	) -> str:
		worker = inspector.worker
		if worker is None:
			return 'starting'
		if worker.finished.is_set():
			return 'stopped'
		if worker.stopping.is_set():
			return 'stopping'
		if not worker.running.is_set():
			return 'starting'
		return 'running'

	def healthy(
		self,
		inspector: 'Inspector',
	) -> bool:
		if self.state(inspector) != 'running':
			return False
		worker = inspector.worker
		if worker is None or worker.consumer is None:
			return False
		with self.lock:
			if self.probe is None or self.probe.is_set():
				self.probe = Event()
				try:
					self.logger.debug('Scheduling Ping Consumer probe')
					worker.consumer.call(self.probe.set)
				except Exception as error:
					self.probe = None
					self.logger.error(
						'Ping Consumer probe scheduling failed: error=%s',
						type(error).__name__,
					)
					return False
			probe = self.probe
		responded = probe.wait(self.timeout)
		healthy = responded and self.state(inspector) == 'running'
		self.logger.debug(
			'Ping Consumer probe completed: responded=%s healthy=%s',
			responded,
			healthy,
		)
		return healthy

	def __call__(
		self,
		inspector: 'Inspector',
	) -> Response:
		healthy = self.healthy(inspector)
		state = 'running' if healthy else self.state(inspector)
		if not healthy and state == 'running':
			state = 'unresponsive'
		self.logger.debug(
			'Building Ping response: status=%s state=%s',
			'200' if healthy else '503',
			state,
		)
		return Response(
			'200 OK' if healthy else '503 Service Unavailable',
			dumps({
				'status': state,
			}).encode('utf-8'),
			'application/json; charset=utf-8',
		)
