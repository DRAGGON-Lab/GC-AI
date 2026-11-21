import test from 'node:test';
import assert from 'node:assert/strict';
import { validateNamespace } from '../src/utils/Namespace.js';

test('namespace requires absolute credential-free HTTP(S) identity', () => {
  for (const value of ['', null, 'relative', 'ftp://example.org', 'https://u:p@example.org', 'https://example.org?q=x', 'https://example.org#x', ' https://example.org', 'https://example.org/a b']) {
    assert.ok(validateNamespace(value), String(value));
  }
  assert.equal(validateNamespace('https://example.org/design///'), null);
});
