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
	'HealthCheck',
)

logger = getLogger(__name__)


class HealthCheck(Extension):
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
			raise ValueError('HealthCheck probe timeout must be finite and positive')
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
					worker.consumer.call(self.probe.set)
				except Exception:
					self.probe = None
					logger.exception('HealthCheck could not schedule the consumer health probe')
					return False
			probe = self.probe
		return probe.wait(self.timeout) and self.state(inspector) == 'running'

	def __call__(
		self,
		inspector: 'Inspector',
	) -> Response:
		healthy = self.healthy(inspector)
		state = 'running' if healthy else self.state(inspector)
		if not healthy and state == 'running':
			state = 'unresponsive'
		return Response(
			'200 OK' if healthy else '503 Service Unavailable',
			dumps({
				'status': state,
			}).encode('utf-8'),
			'application/json; charset=utf-8',
		)
