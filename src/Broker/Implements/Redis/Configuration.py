from enum import Enum
from typing import Optional

from DefStream.Broker import Configuration as BaseConfiguration
from .Serializer import (
	Decoder,
	Encoder,
	JavaScriptObjectNotationDecoder,
	JavaScriptObjectNotationEncoder,
)

__all__ = (
	'Configuration',
	'ConnectionType',
)


class ConnectionType(Enum):
	Pool = 'pool'
	Cluster = 'cluster'


class Configuration(BaseConfiguration):
	def __init__(
		self,
		host: str = '127.0.0.1',
		port: int = 6379,
		username: Optional[str] = None,
		password: Optional[str] = None,
		secure: bool = False,
		type: ConnectionType = ConnectionType.Pool,
		max: int = 10,
		database: int = 0,
		timeout: float = 5,
		encode: Optional[Encoder] = None,
		decode: Optional[Decoder] = None,
	):
		if not isinstance(
			type,
			ConnectionType,
		):
			raise ValueError('Redis connection type must be a ConnectionType')
		if max < 1:
			raise ValueError('Redis max connections must be positive')
		if database < 0 or (type == ConnectionType.Cluster and database != 0):
			raise ValueError('Redis database must be non-negative; Cluster requires database 0')
		if timeout <= 0:
			raise ValueError('Redis connection timeout must be positive')
		self.host = host
		self.port = port
		self.username = username
		self.password = password
		self.secure = secure
		self.type = type
		self.max = max
		self.database = database
		self.timeout = timeout
		self.encode = encode if encode is not None else JavaScriptObjectNotationEncoder()
		self.decode = decode if decode is not None else JavaScriptObjectNotationDecoder()
