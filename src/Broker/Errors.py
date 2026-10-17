__all__ = (
	'RemoteError',
)


class RemoteError(RuntimeError):
	def __init__(
		self,
		code: str,
		message: str,
	):
		self.code = code
		self.message = message
		super().__init__(f'{code}: {message}')
