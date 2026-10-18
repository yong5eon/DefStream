from http.client import HTTPConnection
from importlib import import_module
from json import loads
from unittest import (
	TestCase,
	main,
)
from unittest.mock import (
	Mock,
	patch,
)

from DefStream.Inspector import Inspector
from DefStream.Inspector.Extensions import (
	Dashboard,
	Metrics,
)
from DefStream.Worker import (
	Run,
	ThreadPool,
	Worker,
)


class Task(
	Run,
	parameters={'queue': 'dashboard-test'},
):
	def run(self):
		return 1


class DashboardTests(TestCase):
	def setUp(self):
		self.metrics = Metrics('/metrics')
		self.dashboard = Dashboard('/dashboard')
		self.worker = Worker(
			Mock(),
			ThreadPool(1),
		)
		self.worker.add(Task)
		self.task = Task.__module__ + '.' + Task.__qualname__
		self.inspector = Inspector(
			port=0,
			exts=(
				self.dashboard,
				self.metrics,
			),
		)
		self.addCleanup(self.worker.pool.stop)
		self.addCleanup(self.inspector.stop)
		self.inspector.start(self.worker)

	def fetch(
		self,
		path='/dashboard',
		accept='application/json',
		method='GET',
	):
		server = self.inspector.server
		assert server is not None
		connection = HTTPConnection(
			'127.0.0.1',
			server.server_port,
			timeout=5,
		)
		try:
			connection.request(
				method,
				path,
				headers={'Accept': accept},
			)
			response = connection.getresponse()
			return response.status, response.read(), dict(response.getheaders())
		finally:
			connection.close()

	def test_snapshot_is_atomic_detached_and_uses_shared_collector(self):
		self.worker.running.set()
		started = self.metrics.begin(self.task)
		with patch.object(
			import_module('DefStream.Inspector.Extensions.Metrics'),
			'monotonic',
			return_value=started + 0.25,
		):
			self.metrics.end(
				self.task,
				started,
				True,
			)
		started = self.metrics.begin(self.task)
		self.metrics.end(
			self.task,
			started,
			False,
		)
		rejected = self.metrics.begin(self.task)
		self.metrics.end(
			self.task,
			rejected,
			None,
		)
		pending = self.metrics.begin(self.task)
		status, body, headers = self.fetch()
		data = loads(body)
		self.assertEqual(
			status,
			200,
		)
		self.assertTrue(data['running'])
		self.assertEqual(
			(
				data['tasks'][self.task]['active'],
				data['tasks'][self.task]['success'],
				data['tasks'][self.task]['failure'],
			),
			(
				1,
				1,
				1,
			),
		)
		self.assertGreaterEqual(
			data['tasks'][self.task]['duration'],
			0.25,
		)
		self.assertGreaterEqual(
			data['uptime'],
			0,
		)
		self.assertEqual(
			headers['Cache-Control'],
			'no-store',
		)
		self.assertIs(
			self.dashboard.metrics,
			self.metrics,
		)
		data['tasks'][self.task]['success'] = 100
		self.assertEqual(
			self.metrics.tasks[self.task].success,
			1,
		)
		metrics_body = self.fetch('/metrics')[1]
		self.assertIn(
			b'outcome="success"} 1',
			metrics_body,
		)
		self.metrics.end(
			self.task,
			pending,
			None,
		)

	def test_lifecycle_stays_available_during_start_and_shutdown(self):
		self.assertFalse(loads(self.fetch()[1])['running'])
		self.worker.running.set()
		self.assertTrue(loads(self.fetch()[1])['running'])
		self.worker.stopping.set()
		status, body, headers = self.fetch()
		self.assertEqual(
			status,
			200,
		)
		self.assertFalse(loads(body)['running'])

	def test_html_refresh_custom_text_and_http_methods(self):
		dashboard = Dashboard(
			'/dashboard',
			title='<Dashboard> & Metrics',
			description='<script>not HTML</script>',
		)
		dashboard.start(self.inspector)
		self.inspector.exts['/dashboard'] = dashboard
		status, body, headers = self.fetch(accept='text/html')
		self.assertEqual(
			status,
			200,
		)
		self.assertIn(
			b'<title>&lt;Dashboard&gt; &amp; Metrics</title>',
			body,
		)
		self.assertIn(
			b'&lt;script&gt;not HTML&lt;/script&gt;',
			body,
		)
		self.assertIn(
			"connect-src 'self'",
			headers['Content-Security-Policy'],
		)
		with patch.object(
			import_module('DefStream.Inspector.Extensions.Dashboard'),
			'files',
		) as resources:
			resource = resources.return_value.joinpath.return_value
			resource.read_text.side_effect = [
				'<title>{{dashboard_title}}</title>First',
				'<title>{{dashboard_title}}</title>Updated',
			]
			for expected in (
				b'First',
				b'Updated',
			):
				self.assertIn(
					expected,
					self.fetch(accept='text/html')[1],
				)
		status, body, headers = self.fetch(method='HEAD')
		self.assertEqual(
			(
				status,
				body,
			),
			(
				200,
				b'',
			),
		)
		self.assertGreater(
			int(headers['Content-Length']),
			0,
		)
		self.assertEqual(
			self.fetch(method='POST')[0],
			405,
		)

	def test_metrics_dependency_is_explicit_and_unambiguous(self):
		for exts in (
			(),
			(
				Metrics('/one'),
				Metrics('/two'),
			),
		):
			dashboard = Dashboard('/dashboard')
			inspector = Inspector(exts=(
				dashboard,
				*exts,
			))
			inspector.worker = self.worker
			with self.assertRaisesRegex(
				ValueError,
				'exactly one',
			):
				dashboard.start(inspector)

	def test_snapshot_generation_and_empty_tasks(self):
		before = self.metrics.snapshot(self.inspector)
		before['tasks'].clear()
		self.assertIn(
			self.task,
			self.metrics.snapshot(self.inspector)['tasks'],
		)
		self.metrics.start(self.inspector)
		self.assertNotEqual(
			before['instance'],
			self.metrics.snapshot(self.inspector)['instance'],
		)
		self.worker.tasks.clear()
		self.metrics.start(self.inspector)
		self.assertEqual(
			loads(self.fetch()[1])['tasks'],
			{},
		)

	def test_second_minute_boundaries_and_retention(self):
		with patch.object(
			import_module('DefStream.Inspector.Extensions.Metrics'),
			'monotonic',
		) as clock:
			clock.return_value = 100.0
			self.metrics.start(self.inspector)

			def complete(
				start,
				end,
				success,
			):
				clock.return_value = start
				context = self.metrics.begin(self.task)
				clock.return_value = end
				self.metrics.end(
					self.task,
					context,
					success,
				)

			complete(
				100.0,
				100.5,
				True,
			)
			complete(
				110.0,
				159.0,
				False,
			)
			complete(
				159.0,
				159.9,
				True,
			)
			complete(
				159.5,
				160.0,
				True,
			)
			clock.return_value = 160.1
			snapshot = self.metrics.snapshot(self.inspector)
			windows = snapshot['tasks'][self.task]['windows']
			self.assertEqual(
				snapshot['window_end'],
				160,
			)
			self.assertEqual(
				windows['1']['success'],
				1,
			)
			self.assertEqual(
				windows['1']['failure'],
				1,
			)
			self.assertAlmostEqual(
				windows['1']['duration'],
				49.9,
			)
			self.assertEqual(
				windows['1']['max_duration'],
				49,
			)
			self.assertEqual(
				windows['60']['success'],
				2,
			)
			self.assertAlmostEqual(
				windows['60']['duration'],
				50.4,
			)
			clock.return_value = 161.0
			windows = self.metrics.snapshot(self.inspector)['tasks'][self.task]['windows']
			self.assertEqual(
				windows['1']['success'],
				1,
			)
			self.assertEqual(
				windows['60']['success'],
				2,
			)
			self.assertNotIn(
				100,
				self.metrics.tasks[self.task].buckets,
			)
			clock.return_value = 221.0
			windows = self.metrics.snapshot(self.inspector)['tasks'][self.task]['windows']
			self.assertEqual(
				windows['60'],
				{
					'success': 0,
					'failure': 0,
					'duration': 0,
					'max_duration': 0,
				},
			)
			self.assertFalse(self.metrics.tasks[self.task].buckets)
			for second in range(222, 422):
				complete(
					float(second),
					second + 0.5,
					True,
				)
			self.assertLessEqual(
				len(self.metrics.tasks[self.task].buckets),
				61,
			)

	def test_oldest_pending_collision_and_rejected_submission(self):
		with patch.object(
			import_module('DefStream.Inspector.Extensions.Metrics'),
			'monotonic',
		) as clock:
			clock.return_value = 100.0
			self.metrics.start(self.inspector)
			first = self.metrics.begin(self.task)
			second = self.metrics.begin(self.task)
			clock.return_value = 105.0
			self.metrics.end(
				self.task,
				first,
				None,
			)
			task = self.metrics.snapshot(self.inspector)['tasks'][self.task]
			self.assertEqual(
				task['oldest_active'],
				5,
			)
			self.assertEqual(
				task['active'],
				1,
			)
			self.assertEqual(
				task['windows']['1']['success'],
				0,
			)
			self.metrics.end(
				self.task,
				second,
				True,
			)
			self.assertFalse(self.metrics.tasks[self.task].starts)
			clock.return_value = 106.0
			task = self.metrics.snapshot(self.inspector)['tasks'][self.task]
			self.assertEqual(
				task['oldest_active'],
				0,
			)
			self.assertEqual(
				task['windows']['1']['success'],
				1,
			)
			self.assertEqual(
				task['windows']['1']['duration'],
				5,
			)
			text = self.metrics.render(self.inspector)
			self.assertIn(
				'window_seconds="1",outcome="success"} 1',
				text,
			)


if __name__ == '__main__':
	main()
