# -*- coding: utf-8 -*-

from .Validator import Validator
from .Patterns import IsObject
from .Patterns.Object import IsMappingOf

from functools import wraps
from inspect import signature

__all__ = (
	'Validate',
)


class Validate(object):
	"""Decorator for Validator of Function and Method"""
	def __init__(self, mappings: dict):
		self.mappings = mappings
		return

	def __call__(self, fn: callable):
		@wraps(fn)
		def wrapper(*args, **kwargs):
			validator = Validator(IsObject(IsMappingOf(self.mappings)))
			bound = signature(fn).bind(*args, **kwargs)
			bound.apply_defaults()
			bound.arguments = validator(dict(bound.arguments))
			return fn(*bound.args, **bound.kwargs)
		return wrapper
