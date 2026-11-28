#!/usr/bin/env python3
import base64
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('android_patch', Path(__file__).with_name('patch_libvlc_android.py'))
android = importlib.util.module_from_spec(spec)
spec.loader.exec_module(android)


class AndroidCpuFeaturesTest(unittest.TestCase):
    def test_verified_download_is_cached_and_keeps_the_license(self):
        sources = {'cpu-features.c': b'/* source */\n', 'cpu-features.h': b'/* BSD license */\n'}
        hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()}
        urls = []
        def fetch(url, timeout):
            urls.append(url)
            name = url.split('/')[-1].split('?')[0]
            return io.BytesIO(base64.b64encode(sources[name]))
        with tempfile.TemporaryDirectory() as tmp, patch.dict(android.CPU_FEATURES_SHA256, hashes):
            directory = Path(tmp)
            android.ensure_cpu_features(directory, fetch)
            self.assertEqual(len(urls), 2)
            self.assertTrue(all(android.CPU_FEATURES_REVISION in url for url in urls))
            self.assertEqual((directory / 'NOTICE').read_text(), '/* BSD license */\n')
            android.ensure_cpu_features(directory, lambda *a, **k: self.fail('verified cache must not download'))

    def test_checksum_mismatch_is_rejected_before_publishing(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                android.ensure_cpu_features(directory, lambda *a, **k: io.BytesIO(base64.b64encode(b'corrupt')))
            self.assertFalse((directory / 'cpu-features.c').exists())

    def test_real_recipe_quote_forms_are_relocated_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            rule = Path(tmp) / 'rules.mak'
            rule.write_text('cp "${ANDROID_NDK}"/sources/android/cpufeatures/cpu-features.c vpx_ports\n'
                            'cp "${ANDROID_NDK}/sources/android/cpufeatures/cpu-features.h" include\n')
            directory = Path(tmp) / 'path with spaces'
            android.patch_cpu_features_rule(rule, directory)
            first = rule.read_text()
            self.assertNotIn('ANDROID_NDK', first)
            self.assertIn('"$(OPX_CPUFEATURES_DIR)"/cpu-features.c', first)
            self.assertIn('"$(OPX_CPUFEATURES_DIR)/cpu-features.h"', first)
            android.patch_cpu_features_rule(rule, directory)
            self.assertEqual(rule.read_text(), first)


if __name__ == '__main__':
    unittest.main()
