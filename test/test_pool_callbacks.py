from concurrent.futures import Future
from os import getpid
from queue import Queue
from unittest import (
	TestCase,
	main,
)
from unittest.mock import Mock

from src.Worker import (
	Pool,
	ProcessPool,
	Run,
	ThreadPool,
)


class CallbackRunner(Run):
	def run(
		self,
		fail=False,
	):
		if fail:
			raise ValueError('callback failure')
		return getpid()


class CallbackTests(TestCase):
	def test_callbacks_run_in_parent_for_both_pools(self):
		for pool_class in (
			ThreadPool,
			ProcessPool,
		):
			with self.subTest(pool=pool_class):
				pool = pool_class(1)
				outcomes = Queue()

				def success(result):
					outcomes.put((
						'success',
						getpid(),
						result,
					))

				def failure(error):
					outcomes.put((
						'failure',
						getpid(),
						error,
					))

				try:
					pool.submit(
						CallbackRunner,
						{},
						callback=success,
						error_callback=failure,
					)
					outcome = outcomes.get(timeout=15)
					self.assertEqual(
						outcome[:2],
						(
							'success',
							getpid(),
						),
					)
					if pool_class is ProcessPool:
						self.assertNotEqual(
							outcome[2],
							getpid(),
						)
					pool.submit(
						CallbackRunner,
						{'fail': True},
						callback=success,
						error_callback=failure,
					)
					outcome = outcomes.get(timeout=15)
					self.assertEqual(
						outcome[:2],
						(
							'failure',
							getpid(),
						),
					)
					self.assertIsInstance(
						outcome[2],
						ValueError,
					)
					self.assertTrue(outcomes.empty())
				finally:
					pool.stop()

	def test_already_completed_future_dispatches_callback_once(self):
		future = Future()
		future.set_result('done')
		executor = Mock()
		executor.submit.return_value = future
		pool = Pool(
			executor,
			1,
		)
		success = Mock()
		failure = Mock()
		self.assertIs(
			pool.submit(
				CallbackRunner,
				{},
				callback=success,
				error_callback=failure,
			),
			future,
		)
		success.assert_called_once_with('done')
		failure.assert_not_called()
		self.assertEqual(
			pool.count(),
			0,
		)


if __name__ == '__main__':
	main()
