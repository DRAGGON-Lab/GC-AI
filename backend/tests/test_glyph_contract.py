"""One executed contract spanning detector YAML, Python, JavaScript and backend."""
import json
import subprocess
from pathlib import Path

import yaml
from gcai.constants import GLYPH_TO_ROLE, RNA_ROLES as CLIENT_RNA
from app.utils.validation import ROLES, RNA_ROLES

ROOT = Path(__file__).resolve().parents[2]


def test_all_foreground_glyphs_have_explicit_cross_language_roles():
    config = yaml.safe_load((ROOT / 'backend/app/data_configs/glyphs.yaml').read_text())
    declared = config['CLASSES']
    assert declared[0] == '__background__'
    assert config['NC'] == len(declared) == 15
    result = subprocess.run(['node', '--input-type=module', '-e',
        "import {GLYPH_TO_ROLE,updatePredictions} from './frontend/src/utils/PredictionUtils.js';"
        "console.log(JSON.stringify({mapping:GLYPH_TO_ROLE,background:updatePredictions({pred_classes:['__background__'],draw_boxes:[[0,0,1,1]]},{})}));"],
        cwd=ROOT, capture_output=True, text=True, check=True)
    js = json.loads(result.stdout)
    python = {glyph.value: role.value for glyph, role in GLYPH_TO_ROLE.items()}
    assert {name.lower() for name in declared[1:]} == set(js['mapping'])
    assert js['mapping'] == {glyph.lower(): role for glyph, role in python.items()}
    assert set(js['mapping'].values()) <= ROLES | RNA_ROLES
    assert {role.value for role in CLIENT_RNA} == RNA_ROLES
    assert [row['id'] for row in js['background']] == ['component-principal']
    assert js['mapping']['cds-arrow'] == 'CDS'
    assert js['mapping']['ncrna'] in RNA_ROLES
