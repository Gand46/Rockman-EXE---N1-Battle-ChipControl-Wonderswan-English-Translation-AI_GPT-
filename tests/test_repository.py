"""Repository layout, safety and edit-preservation contract. No ROM needed."""
from pathlib import Path
import importlib.util
import json
import tempfile
import unittest
from unittest import mock
import sys

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('project_cli',ROOT/'scripts/project.py')
repo=importlib.util.module_from_spec(spec);spec.loader.exec_module(repo)

class RepositoryTests(unittest.TestCase):
    def test_current_patch_paths_are_unique(self):
        variants=repo.config()['current']['variants']; self.assertEqual(set(variants),{'qa09','chip-control'})
        self.assertNotEqual(variants['qa09']['patch'],variants['chip-control']['patch'])
        self.assertEqual(len(list((ROOT/'patches').rglob('*.bps'))),2)
        self.assertFalse(list((ROOT/'patches').rglob('*.ips')))

    def test_default_is_only_qa09(self):
        self.assertTrue(repo.config()['current']['variants']['qa09']['default'])
        self.assertFalse(repo.config()['current']['variants']['chip-control']['default'])

    def test_patch_payloads_unchanged(self):
        for v in repo.config()['current']['variants'].values():
            self.assertEqual(repo.sha((ROOT/v['patch']).read_bytes()),v['bps_sha256'])

    def test_no_fake_top_level_source_folders(self):
        for name in ('src','formats','resources','localization','optional','translation'):
            self.assertFalse((ROOT/name).exists(),name)

    def test_no_historical_root_launchers(self):
        self.assertEqual(list(ROOT.glob('BUILD*.bat')),[])
        self.assertEqual(list(ROOT.glob('README_QA*.md')),[])

    def test_single_workflow(self):
        paths=list((ROOT/'.github/workflows').glob('*.yml'));self.assertEqual(len(paths),1)
        text=paths[0].read_text()
        self.assertIn('contents: read',text)
        self.assertIn('persist-credentials: false',text)
        self.assertEqual(text.count('uses: actions/'),2)
        self.assertNotIn('pull_request_target',text)

    def test_editor_and_lineage_are_differentiated(self):
        q=ROOT/'components/qa09/translation'
        self.assertTrue((q/'en_qa09.json').is_file())
        self.assertEqual([p.name for p in q.glob('en_*.json')],['en_qa09.json'])
        self.assertTrue((q/'lineage/en_qa08.json').is_file())

    def test_forbidden_extensions_covered(self):
        self.assertTrue({'.wsc','.sav','.srm','.so','.exe','.ttf'}<=repo.BANNED)

    def test_inventory_ignores_transient_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d);(r/'build').mkdir();(r/'build/test.wsc').write_bytes(b'private')
            (r/'source.py').write_text('x=1\n')
            self.assertEqual(set(repo.inventory(r)),{'source.py'})

    def test_source_changes_detected_by_hash(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d);p=r/'source.py';p.write_text('x=1\n');a=repo.inventory(r)
            p.write_text('x=2\n');self.assertNotEqual(a,repo.inventory(r))

    def test_wrong_source_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'wrong.wsc';p.write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError,'Wrong original'):repo.original(p)

    def test_wrong_source_creates_no_build_output(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'wrong.wsc';p.write_bytes(b'wrong');out=Path(d)/'out'
            with self.assertRaises(ValueError):repo.build(p,'qa09',out)
            self.assertFalse(out.exists())

    def test_output_inside_editable_sources_rejected(self):
        with self.assertRaises(ValueError):repo.output_guard(ROOT/'components/qa09/translation',Path('/unused/input.wsc'))

    def test_output_inside_repository_root_rejected(self):
        with self.assertRaises(ValueError):repo.output_guard(ROOT,Path('/unused/input.wsc'))

    def test_modified_qa09_cannot_silently_enter_rc6(self):
        with self.assertRaisesRegex(ValueError,'not eligible'):repo.build(Path('/missing'),'chip-control',modified=True)

    def test_qa09_build_does_not_load_rc6_adapter(self):
        # Inspect the control boundary: the default path does not require an optional vendor file.
        text=(ROOT/'scripts/project.py').read_text()
        self.assertIn('if key == "qa09":',text)
        new=(ROOT/'scripts/build_mant04.py').read_text()
        self.assertIn('needs_rc6="chip-control" in targets',new)
        self.assertIn("'all' if needs_rc6 else 'qa09'",new)
        self.assertIn('default="qa09"',text)

    def test_no_source_assembly_completeness_claim_for_rc6(self):
        c=repo.config()['current']['variants']['chip-control']
        self.assertFalse(c['editable_rc6_assembly'])
        self.assertEqual(c['redistribution_permission'],'NOT_DOCUMENTED')

    def test_asset_refs_remain_local(self):
        q=ROOT/'components/qa09/translation';m=json.loads((q/'en_qa09.json').read_text())
        self.assertEqual(len(m['binary_entries']),84)
        for e in m['binary_entries']:
            p=(q/e['asset']).resolve();self.assertTrue(p.is_relative_to(q));self.assertTrue(p.is_file())

    def test_current_docs_links(self):
        self.assertEqual(repo.documentation_links()['broken_local_links'],0)

if __name__=='__main__':unittest.main()
