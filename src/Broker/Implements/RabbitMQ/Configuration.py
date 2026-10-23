# -*- coding: utf-8 -*-

from DefStream.Broker import Configuration as BaseConfiguration

from .Serializer import (
	Encoder,
	Decoder,
	JavaScriptObjectNotationEncoder,
	JavaScriptObjectNotationDecoder,
)


from pika import SSLOptions
from ssl import create_default_context

__all__ = (
	'Configuration'
)


class Configuration(BaseConfiguration):
	"""
	Configuration of Event Broker for RabbitMQ
	"""
	def __init__(
		self,
		host: str,
		port: int,
		username: str = None,
		password: str = None,
		ssl: bool = False,
		vhost: str = '/',
		timeout: int = None,
		heartbeat: int = None,
		encode: Encoder = JavaScriptObjectNotationEncoder(),
		decode: Decoder = JavaScriptObjectNotationDecoder(),
	):
		self.host = host
		self.port = port
		self.username = username
		self.password = password
		self.ssl = SSLOptions(create_default_context(), host) if ssl else None
		self.vhost = vhost
		self.timeout = timeout/1000 if timeout else None
		self.heartbeat = int(heartbeat*2/1000) if heartbeat else None
		self.encode = encode
		self.decode = decode
		return
