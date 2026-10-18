from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import Mock, patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import device_identity as identity


class IdentityTests(unittest.TestCase):
    def response(self, data):
        response=Mock()
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=False)
        response.read.return_value=json.dumps(data).encode()
        return response

    def test_name_rules_and_spacing(self):
        self.assertEqual(identity.clean_label('  Caucel   04 '), 'Caucel 04')
        for name in ('', 'ab', 'x'*41, 'bad/name', 'bad\"name'):
            with self.assertRaises(ValueError):identity.clean_label(name)

    def test_available_name_sends_hash_not_raw_serial(self):
        with patch.object(identity.urllib.request,'urlopen',return_value=self.response({'available':True})) as get:
            result=identity.check_label('Caucel4',serial='private-serial')
        self.assertTrue(result['checked'])
        self.assertFalse(result['reserved'])
        self.assertNotIn('private-serial',get.call_args.args[0].full_url)
        self.assertIn('device=',get.call_args.args[0].full_url)

    def test_duplicate_blocked_and_own_name_accepted(self):
        with patch.object(identity.urllib.request,'urlopen',return_value=self.response({'available':False})):
            with self.assertRaises(identity.NameTaken):identity.check_label('Caucel4',serial='other')
        with patch.object(identity.urllib.request,'urlopen',return_value=self.response({'available':True,'same_device':True})):
            self.assertTrue(identity.check_label('Caucel4',serial='same')['same_device'])

    def test_offline_or_invalid_response_is_not_available(self):
        with patch.object(identity.urllib.request,'urlopen',side_effect=OSError()):
            with self.assertRaises(identity.NameCheckUnavailable):identity.check_label('Caucel4',serial='same')
        with patch.object(identity.urllib.request,'urlopen',return_value=self.response({'unexpected':True})):
            with self.assertRaises(identity.NameCheckUnavailable):identity.check_label('Caucel4',serial='same')

    def test_label_update_preserves_other_secrets_and_single_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'runtime.env'
            p.write_text('GDF_HEALTH_TOKEN=private-value\nGDF_HEALTH_LABEL=old\n')
            identity.save_label(p,'Caucel 4')
            values=identity.runtime_values(p)
            self.assertEqual(values['GDF_HEALTH_TOKEN'],'private-value')
            self.assertEqual(values['GDF_HEALTH_LABEL'],'Caucel 4')
            self.assertEqual(p.read_text().count('GDF_HEALTH_LABEL='),1)
