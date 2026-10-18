"""QA13/MANT04 binary-scope and source-safety regression tests.

ROM-dependent tests require the user's verified Japanese base via
CONTINUITY_INPUT_JP; they are never run against bundled ROMs.
"""
from __future__ import annotations
import json, os, sys, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import project, qa13_visual_repair as visual

class QA13VisualRepairs(unittest.TestCase):
    def test_canonical_project_source_exists(self):
        self.assertTrue((ROOT/'components/qa09/translation/qa03/compact_display_font.json').is_file())
        self.assertEqual(project.config()['original']['sha256'],
                         '4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed')

    def test_mask_coverage_for_labels(self):
        masks=visual.native_masks()
        for text in ('1 CHIP','10 CHIPS','INFO','SHOP','HOST TOURNEY','FREE BATTLE'):
            self.assertFalse(set(text)-set(masks)-{' '})
        self.assertTrue(all(len(a)==7 and len({len(r) for r in a})==1 for a in masks.values()))

    def test_no_opaque_runtime_inputs(self):
        code=(ROOT/'scripts/qa13_visual_repair.py').read_text()
        self.assertNotIn('ImageFont.truetype',code)
        self.assertIn('all_original_glyph_rows_unchanged',code)
        self.assertIn('font_region_unchanged',code)

    def test_static_provenance_is_explicit(self):
        p=ROOT/'docs/evidence/qa13/native_netnavi_provenance.json'
        d=json.loads(p.read_text())
        self.assertEqual(d['decision'],'PRESERVE_ORIGINAL')
        self.assertTrue(all(r['map_match'] and r['tile_match'] for r in d['records']))

    @classmethod
    def setUpClass(cls):
        s=os.environ.get('CONTINUITY_INPUT_JP')
        cls.source=Path(s) if s else None
        cls.qa=ROOT/'build/mant04/qa09/Rockman_N1_English_QA09_MANT04.wsc'
        cls.cc=ROOT/'build/mant04/chip-control/Rockman_N1_English_QA09_ChipControl_RC6_MANT04_EXPERIMENTAL.wsc'

    def get_roms(self):
        if not self.source or not self.source.exists():self.skipTest('requires verified original Japanese ROM')
        if not self.qa.is_file() or not self.cc.is_file():self.skipTest('run scripts/build_mant04.py first')
        return project.original(self.source),self.qa.read_bytes(),self.cc.read_bytes()

    def test_two_published_bps_roundtrip(self):
        original,qa,cc=self.get_roms()
        _,_,apply_bps=project.qa_modules()
        cfg=project.config()
        for variant,entry in cfg.get('predecessor',cfg['current'])['variants'].items():
            self.assertEqual(apply_bps(original,(ROOT/entry['patch']).read_bytes()),qa if variant=='qa09' else cc)

    def test_edited_visual_spans_and_gameplay_preserved(self):
        _,qa,_=self.get_roms()
        base=ROOT/'build/mant04/original_rebuild/qa09/Rockman_N1_English_QA09.wsc'
        if not base.exists():self.skipTest('exact QA09 baseline missing')
        base=base.read_bytes()
        outcome,report=visual.apply(base)
        self.assertEqual(outcome,qa)
        self.assertEqual(report['outside_allowed'],0)
        self.assertTrue(report['font_region_unchanged'])
        self.assertTrue(report['netnavi']['changed_bytes']==0)
        self.assertTrue(all(g['edits']>0 for g in report['groups']))

    def test_chip_control_diff_exactly_same_as_qa_visual_diff(self):
        _,qa,cc=self.get_roms()
        base=(ROOT/'build/mant04/original_rebuild/qa09/Rockman_N1_English_QA09.wsc').read_bytes()
        rc=(ROOT/'build/mant04/original_rebuild/chip-control/Rockman_N1_English_QA09_ChipControl_RC6_EXPERIMENTAL.wsc').read_bytes()
        a={i for i in range(len(qa)-2) if qa[i]!=base[i]}
        b={i for i in range(len(cc)-2) if cc[i]!=rc[i]}
        self.assertEqual(a,b)
        self.assertTrue(all(base[i]==rc[i] for i in a))
        for data in (qa,cc):self.assertEqual(int.from_bytes(data[-2:],'little'),sum(data[:-2])&0xffff)

    def test_wrong_baseline_refused(self):
        _,_,_=self.get_roms()
        fake=bytearray((ROOT/'build/mant04/original_rebuild/qa09/Rockman_N1_English_QA09.wsc').read_bytes())
        fake[0x1200]^=1
        with self.assertRaisesRegex(ValueError,'exact QA09 MANT03'):
            visual.apply(bytes(fake))

    def test_pet_font_identity_is_lossless_rebaseline(self):
        _,qa,_=self.get_roms()
        old=(ROOT/'build/mant04/original_rebuild/qa09/Rockman_N1_English_QA09.wsc').read_bytes()
        mo,to=0x042DBA,0x07C330
        items=[(2,2,8,2),(2,5,7,2),(2,8,8,2),(2,11,5,2),(2,14,3,2)]
        for x,y,w,h in items:
            before=visual.from_rect(old[mo:mo+0x400],old[to:to+0x980],x,y,w,h,1)
            after=visual.from_rect(qa[mo:mo+0x400],qa[to:to+0x980],x,y,w,h,1)
            self.assertEqual(after[:6],[[9]*(w*8)]*6)
            self.assertEqual(after[6:],before[:10])

if __name__=='__main__':unittest.main()
