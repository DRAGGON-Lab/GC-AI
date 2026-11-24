#!/usr/bin/env python3
"""Run outside the checkout with installed wheels or source distributions."""
import io
import json
from pathlib import Path
import tempfile
import zipfile


def main():
    from importlib.metadata import entry_points, version
    import app
    from app import config
    from app.wsgi import application
    import gcai
    import sbol3

    if config.model is not None:
        raise RuntimeError('Installed WSGI import eagerly loaded the detector')
    if not Path(config.GLYPHS_CONFIG_PATH).is_file() or config.NUM_CLASSES != 15:
        raise RuntimeError('Installed package is missing its detector YAML')
    scripts = {entry.name: entry for entry in entry_points(group='console_scripts')}
    for name in ['gc-ai-backend', 'gc-ai-janitor', 'gcai']:
        if not callable(scripts[name].load()):
            raise RuntimeError(f'Broken installed entrypoint: {name}')
    with tempfile.TemporaryDirectory(prefix='gcai-installed-') as root:
        application.config.update(TESTING=True, FILES_GENERATED_DIR=str(Path(root) / 'artifacts'))
        client = application.test_client()
        assert client.get('/livez').status_code == 200
        data = {'namespace': 'https://example.org/installed', 'components': [
            {'name': 'Design', 'role': 'Engineered-Region', 'new': True, 'uri': 'https://example.org/'},
            {'name': 'Part', 'role': 'CDS', 'new': True, 'uri': 'https://example.org/', 'sequence': 'ATGC'},
        ], 'expressions': [], 'interactions': [], 'eds': []}
        response = client.post('/file/create', json=data)
        assert response.status_code == 200, response.json
        document = sbol3.Document()
        document.read_string(response.data.decode(), 'xml')
        assert len(document.validate()) == 0
        assert document.find('https://example.org/installed/Design').sequences[0].lookup().elements == 'atgc'
        converted = client.post('/file/convert', json={
            'structural_handle': response.headers['X-GCAI-Structural-Handle'], 'fasta': True, 'genbank': True,
        })
        assert converted.status_code == 200, converted.json
        with zipfile.ZipFile(io.BytesIO(converted.data)) as archive:
            assert len(archive.namelist()) == 2
            assert any(name.endswith('.fasta') for name in archive.namelist())
            assert any(name.endswith('.gb') for name in archive.namelist())
    print(json.dumps({'result': 'passed', 'backend': version('gc-ai-backend'),
                      'client': version('gc-ai-client'), 'backend_path': app.__file__, 'client_path': gcai.__file__}))


if __name__ == '__main__':
    main()
