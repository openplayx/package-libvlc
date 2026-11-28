import json
from pathlib import Path
import tempfile
import unittest

from fix_vlc_config import fix, LINE


class ConfigureStringTest(unittest.TestCase):
    def test_quoted_windows_paths_and_crlf_are_preserved(self):
        value = 'configure AV_LIBS="C:/ci/foo.dll.a" FLAG=C:\\cache\\x'
        raw = value.replace('\\', '\\\\')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.h'
            path.write_bytes(('#define OTHER 1\r\n#define CONFIGURE_LINE "' + raw + '"\r\n').encode())
            self.assertTrue(fix(path))
            result = path.read_bytes()
            self.assertTrue(result.startswith(b'#define OTHER 1\r\n'))
            self.assertTrue(result.endswith(b'\r\n'))
            self.assertEqual(value, json.loads(LINE.search(result.decode())[2]))
            self.assertFalse(fix(path))
            self.assertEqual(result, path.read_bytes())

    def test_valid_string_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.h'
            path.write_bytes(b'#define CONFIGURE_LINE "configure --enable-foo"\n')
            before = path.stat().st_mtime_ns
            self.assertFalse(fix(path))
            self.assertEqual(before, path.stat().st_mtime_ns)


if __name__ == '__main__':
    unittest.main()
