import json
import sys
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from registry import Manifest, decide, inspect_image


SHA_A = 'sha256:' + 'a'*64
SHA_B = 'sha256:' + 'b'*64


def m(digest=SHA_A, platforms=('linux/amd64', 'linux/arm64')):
    return Manifest(digest, frozenset(platforms))


class RegistryTests(unittest.TestCase):
    def test_first_publication_builds(self):
        self.assertEqual(decide(None, None, {'linux/amd64'}, True, False), 'build')

    def test_missing_architecture_rebuilds(self):
        self.assertEqual(decide(m(platforms=('linux/amd64',)), m(), {'linux/amd64', 'linux/arm64'}, True, False), 'build')

    def test_same_digest_skips(self):
        self.assertEqual(decide(m(), m(), {'linux/amd64', 'linux/arm64'}, True, False), 'skip')

    def test_stale_latest_retags(self):
        self.assertEqual(decide(m(), m(SHA_B), {'linux/amd64'}, True, False), 'retag')

    def test_missing_latest_retags(self):
        self.assertEqual(decide(m(), None, {'linux/amd64'}, True, False), 'retag')

    def test_fixed_version_ignores_latest(self):
        self.assertEqual(decide(m(), m(SHA_B), {'linux/amd64'}, False, False), 'skip')

    def test_force_rebuilds(self):
        self.assertEqual(decide(m(), m(), {'linux/amd64'}, True, True), 'build')

    @patch('registry.subprocess.run')
    def test_index_ignores_attestations(self, run):
        run.return_value = CompletedProcess([], 0, stdout=json.dumps({
            'digest': SHA_A, 'manifests': [
                {'platform': {'os': 'linux', 'architecture': 'amd64'}},
                {'platform': {'os': 'linux', 'architecture': 'arm64'}},
                {'platform': {'os': 'unknown', 'architecture': 'unknown'}},
            ]
        }), stderr='')
        self.assertEqual(inspect_image('ghcr.io/owner/image:v1').platforms, frozenset({'linux/amd64', 'linux/arm64'}))

    @patch('registry.subprocess.run')
    def test_missing_tag(self, run):
        run.return_value = CompletedProcess([], 1, stdout='', stderr='manifest unknown')
        self.assertIsNone(inspect_image('ghcr.io/owner/image:v1'))

    @patch('registry.subprocess.run')
    def test_unexpected_registry_error_fails(self, run):
        run.return_value = CompletedProcess([], 1, stdout='', stderr='401 Unauthorized')
        with self.assertRaisesRegex(RuntimeError, '401'):
            inspect_image('ghcr.io/owner/image:v1')


if __name__ == '__main__':
    unittest.main()
