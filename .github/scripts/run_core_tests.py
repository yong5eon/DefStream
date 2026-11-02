from pathlib import Path
from sys import (
	exit,
	path as module_path,
)
from unittest import TestLoader, TextTestRunner

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
	module_path.insert(
		0,
		str(ROOT),
	)
	modules: list[str] = [
		f'tests.{test_file.stem}'
		for test_file in sorted((ROOT / 'tests').glob('test_*.py'))
	]
	suite = TestLoader().loadTestsFromNames(modules)
	result = TextTestRunner(verbosity=2).run(suite)
	return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
	exit(main())
