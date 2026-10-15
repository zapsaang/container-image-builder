import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from config import read_config
from plan import make_plan
from resolve import resolve


class BuildConfigTests(unittest.TestCase):
    def test_plan_skips_disabled_images(self):
        root = Path(__file__).resolve().parents[1] / 'images'
        self.assertEqual([v['name'] for v in make_plan(root, 'all')], ['ssh-mcp'])

    def test_missing_image_is_error(self):
        with self.assertRaises(ValueError):
            make_plan(Path(__file__).resolve().parents[1] / 'images', 'missing')

    def test_config_blocks_path_traversal(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'escape.json'
            p.write_text(json.dumps({
                'name': 'escape', 'repository': 'a/b',
                'version': {'strategy': 'tag', 'tag': 'v1'},
                'build': {'dockerfile': '../Dockerfile'}
            }))
            with self.assertRaisesRegex(ValueError, 'within the upstream'):
                read_config(p)

    def test_fixed_tag_cannot_move_latest(self):
        with self.assertRaisesRegex(ValueError, 'latest'):
            resolve('a/b', 'tag', 'v1', 'Example', 'ssh-mcp', True, '')

    def test_fixed_tag_resolves(self):
        result = resolve('a/b', 'tag', 'v1', 'Example', 'ssh-mcp', False, '')
        self.assertEqual(result['image'], 'ghcr.io/example/ssh-mcp')
        self.assertEqual(result['tags'], ['ghcr.io/example/ssh-mcp:v1'])


if __name__ == '__main__':
    unittest.main()
