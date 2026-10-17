"""Guardrails of the RC6/QA09 scoped port; no emulator or original ROM needed for basic tests."""
import importlib.util, pathlib, unittest, sys, zlib, hashlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('verify',ROOT/'src/verify_and_build_experimental.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class TestPort(unittest.TestCase):
 def test_ips_parser(self):
  b=b'PATCH'+b'\x00\x00\x07\x00\x03ABC'+b'EOF'
  r=m.parse_ips(b);self.assertEqual(r,[(7,b'ABC')]);self.assertEqual(m.apply_ips(b'_'*16,r),b'_______ABC______')
 def test_ips_reject_invalid(self):
  for b in (b'',b'PATCH\0\0',b'PATCH\x3f\xff\xfe\x00\x03ABC' +b'EOF'):
   with self.assertRaises(ValueError):m.parse_ips(b)
 def test_bps_roundtrip(self):
  a=b'abcdef'*100;b=a[:32]+b'changed'+a[39:]
  p=m.build_bps(a,b);self.assertEqual(m.apply_bps(a,p),b)
 def test_bps_bad_crc(self):
  a=b'abcdef';p=bytearray(m.build_bps(a,a));p[-1]^=1
  with self.assertRaises(ValueError):m.apply_bps(a,bytes(p))
 def test_rc6_inputs_are_consistent(self):
  d=ROOT.parents[1]/'patches/qa09'
  for name,expect in [('Rockman_N1_English_QA09.bps',m.QA09_BPS_SHA),('Rockman_EXE_N1_Battle_English_v0.10.7-graphics-a9.ips',m.A9_IPS_SHA)]:
   self.assertEqual(m.sha(((d/name) if name.endswith('.bps') else (ROOT/'vendor'/name)).read_bytes()),expect)
  name='ChipControl_v0.5.8_RC6_for_English_v0.10.7-graphics-a9.ips'
  self.assertEqual(m.sha((ROOT/'vendor'/name).read_bytes()),m.RC6_IPS_SHA)
 def test_hash_gate_rejects_wrong_jp(self):
  with self.assertRaisesRegex(ValueError,'original Japanese ROM'):
   m.analyse(b'bad',b'',b'',b'')
 def test_hash_gate_rejects_modified_rc6(self):
  # A 4MB synthetic Japanese ROM would require the real hash; the SHA guard is exercised directly.
  with self.assertRaises(ValueError):m.require_equal('bad',m.RC6_IPS_SHA,'ChipControl RC6 IPS')

if __name__=='__main__':unittest.main()
