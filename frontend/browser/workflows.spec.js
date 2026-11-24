/* eslint-env node */
import { test as base, expect } from '@playwright/test';
import JSZip from 'jszip';

const pixel = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jWZkAAAAASUVORK5CYII=';
const handle = 'v1_' + 'A'.repeat(43);
export const test = base.extend({
  page: async ({ page }, use) => {
    const unexpected = [];
    const errors = [];
    page.on('request', request => {
      const url = new URL(request.url());
      if (!url.pathname.startsWith('/api/')) return;
      const methods = { '/api/component/names': 'GET', '/api/component/details': 'GET',
        '/api/component/interactions': 'GET', '/api/inference/': 'POST',
        '/api/file/create': 'POST', '/api/file/convert': 'POST' };
      if (url.origin !== 'http://127.0.0.1:4173' || request.method() !== methods[url.pathname]) {
        unexpected.push(request.method() + ' ' + url.href);
      }
      if (url.pathname === '/api/inference/' && !request.headers()['content-type']?.startsWith('multipart/form-data;')) {
        unexpected.push('Inference must upload multipart image data');
      }
    });
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin === 'http://127.0.0.1:4173' &&
          (url.pathname === '/' || url.pathname.startsWith('/assets/'))) return route.continue();
      if (url.pathname === '/api/component/names') return route.fulfill({ json: ['BBa_A', 'BBa_B'] });
      if (url.pathname === '/api/inference/') return route.fulfill({ json: {
        pred_classes: ['promoter', 'ribosome-entry-site'],
        draw_boxes: [[1, 1, 10, 10], [20, 1, 30, 10]],
        has_predictions: true, result_image: pixel,
      } });
      unexpected.push(route.request().method() + ' ' + url.href);
      await route.abort();
    });
    await use(page);
    expect(unexpected, 'Every API and external request must be explicitly mocked').toEqual([]);
    expect(errors, 'No uncaught browser exceptions').toEqual([]);
  },
});

export async function upload(page) {
  await page.goto('/');
  await page.locator('#file-input').setInputFiles({ name: 'circuit.png', mimeType: 'image/png', buffer: Buffer.from(pixel, 'base64') });
  await expect(page.getByLabel('Namespace', { exact: false })).toBeVisible();
}

export async function edit(page) {
  await upload(page);
  await page.getByLabel('Namespace', { exact: false }).fill('https://example.org/research');
  for (const [index, name] of ['Circuit', 'PromoterPart', 'RBSPart'].entries()) {
    const accordion = page.locator('.MuiAccordion-root').nth(index);
    await accordion.locator('.MuiAccordionSummary-root').click();
    await accordion.locator('input[type=checkbox]').first().check();
    if (index === 0) {
      const role = accordion.getByRole('combobox', { name: 'Role', exact: true });
      await role.fill('Engineered-Region');
      await role.press('ArrowDown');
      await role.press('Enter');
    }
    await accordion.locator('input[name=uri]').fill('https://example.org/parts/');
    await accordion.locator('input[name=identifier]').fill('id_' + name);
    await accordion.locator('input[name=name]').fill(name);
    await accordion.locator('input[name=description]').fill('Reviewed ' + name);
    if (index) await accordion.locator('input[name=sequence]').fill('ATGC');
  }
}

export async function create(page) {
  // Later versions require explicit human review of the current part list.
  const review = page.getByRole('checkbox', { name: /I have reviewed/ });
  if (await review.count()) await review.check();
  await page.getByRole('button', { name: 'Create SBOL 3 File' }).click();
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
}

test('rendered upload, editing, generation, downloads and conversion', async ({ page }) => {
  let submitted;
  await page.route('**/api/file/create', route => {
    submitted = route.request().postDataJSON();
    return route.fulfill({ body: '<rdf:RDF/>', contentType: 'application/xml', headers: { 'X-GCAI-Structural-Handle': handle } });
  });
  const archive = await new JSZip().file('Circuit_fasta.fasta', '>Circuit\natgc\n').generateAsync({ type: 'nodebuffer' });
  await page.route('**/api/file/convert', route => {
    expect(route.request().postDataJSON()).toEqual({ structural_handle: handle, fasta: true, genbank: false });
    return route.fulfill({ body: archive, contentType: 'application/zip' });
  });
  await edit(page);
  const xml = page.waitForEvent('download');
  await create(page);
  expect((await xml).suggestedFilename()).toBe('Circuit.xml');
  expect(submitted.components.map(part => part.name)).toEqual(['Circuit', 'PromoterPart', 'RBSPart']);
  await page.getByRole('checkbox', { name: 'Convert to FASTA' }).check();
  const fasta = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Convert', exact: true }).click();
  expect((await fasta).suggestedFilename()).toBe('Circuit.fasta');
  await expect(page.getByText('Files converted successfully!', { exact: true })).toBeVisible();
});

for (const failure of [400, 500, 'network']) {
  test(`create ${failure} preserves mounted editors and every draft field`, async ({ page }) => {
    await page.route('**/api/file/create', route => failure === 'network'
      ? route.abort() : route.fulfill({ status: failure, json: { error: 'Synthetic create failure' } }));
    await edit(page);
    await page.locator('input[name=name]').first().evaluate(node => { node.dataset.retained = 'yes'; });
    await create(page);
    await expect(page.getByRole('dialog').last()).toContainText(/failure|kept/);
    await page.keyboard.press('Escape');
    await expect(page.locator('input[name=name]').first()).toHaveValue('Circuit');
    await expect(page.locator('input[name=name]').first()).toHaveAttribute('data-retained', 'yes');
    await expect(page.locator('input[name=description]').nth(1)).toHaveValue('Reviewed PromoterPart');
    await expect(page.locator('input[name=sequence]').first()).toHaveValue('ATGC');
    await expect(page.getByRole('checkbox', { name: 'controlled' }).first()).toBeChecked();
  });
}

test('registry failures allow manual editing, and retry retains successful lists', async ({ page }) => {
  const counts = {};
  let recovered = false;
  await page.route('**/api/component/names?*', route => {
    const role = new URL(route.request().url()).searchParams.get('role');
    counts[role] = (counts[role] || 0) + 1;
    return route.fulfill(role === 'CDS' && !recovered ? { status: 500, json: {} } : { json: ['BBa_A', 'BBa_B'] });
  });
  await edit(page);
  await expect(page.getByText(/Some registry parts could not be loaded/)).toBeVisible();
  recovered = true;
  await page.getByRole('button', { name: 'Retry registry' }).click();
  await expect(page.getByText(/Some registry parts could not be loaded/)).toHaveCount(0);
  await expect(page.locator('input[name=name]').first()).toHaveValue('Circuit');
  expect(counts.Promoter).toBe(1);
  expect(counts.CDS).toBe(2);
});

test('conversion failure retains handle and format selection for retry', async ({ page }) => {
  const attempts = [];
  await page.route('**/api/file/create', route => route.fulfill({ body: '<rdf:RDF/>', headers: { 'X-GCAI-Structural-Handle': handle } }));
  const archive = await new JSZip().file('Circuit_fasta.fasta', '>Circuit\natgc\n').generateAsync({ type: 'nodebuffer' });
  await page.route('**/api/file/convert', route => {
    attempts.push(route.request().postDataJSON());
    return route.fulfill(attempts.length === 1 ? { status: 503, json: { error: 'Retry conversion' } } : { body: archive });
  });
  await edit(page);
  await create(page);
  await page.getByRole('checkbox', { name: 'Convert to FASTA' }).check();
  await page.getByRole('button', { name: 'Convert', exact: true }).click();
  await expect(page.getByText('Retry conversion', { exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('checkbox', { name: 'Convert to FASTA' })).toBeChecked();
  await page.getByRole('button', { name: 'Convert', exact: true }).click();
  await expect(page.getByText('Files converted successfully!', { exact: true })).toBeVisible();
  expect(attempts).toEqual([attempts[0], attempts[0]]);
  expect(attempts[0].structural_handle).toBe(handle);
  await page.keyboard.press('Escape');
  await expect(page.locator('input[name=name]').first()).toHaveValue('Circuit');
});

test('only confirmed New design discards edits', async ({ page }) => {
  await edit(page);
  await page.getByRole('button', { name: 'New design', exact: true }).click();
  await page.getByRole('button', { name: 'Keep editing' }).click();
  await expect(page.locator('input[name=name]').first()).toHaveValue('Circuit');
  await page.getByRole('button', { name: 'New design', exact: true }).click();
  await page.getByRole('button', { name: 'Discard and start new' }).click();
  await expect(page.getByLabel('Namespace', { exact: false })).toHaveCount(0);
  await upload(page);
  await expect(page.getByLabel('Namespace', { exact: false })).toHaveValue('');
});

test('late registry details cannot overwrite a newer selection', async ({ page }) => {
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  await page.route('**/api/component/details?*', async route => {
    const name = new URL(route.request().url()).searchParams.get('component_name');
    if (name === 'BBa_A') await pending;
    await route.fulfill({ json: { name, identifier: name, role: 'Promoter', sequence: name === 'BBa_A' ? 'AAAA' : 'CCCC', sequence_length: 4, description: name } }).catch(() => {});
  });
  await upload(page);
  const accordion = page.locator('.MuiAccordion-root').nth(1);
  await accordion.locator('.MuiAccordionSummary-root').click();
  const name = accordion.getByRole('combobox', { name: 'Name', exact: true });
  await name.fill('BBa_A');
  await page.getByRole('option', { name: 'BBa_A', exact: true }).click();
  await name.fill('BBa_B');
  await page.getByRole('option', { name: 'BBa_B', exact: true }).click();
  await expect(accordion.locator('input[name=sequence]')).toHaveValue('CCCC');
  release();
  await expect(accordion.locator('input[name=identifier]')).toHaveValue('BBa_B');
  await page.getByRole('button', { name: 'New design', exact: true }).click();
  await page.getByRole('button', { name: 'Discard and start new' }).click();
  await expect(page.getByLabel('Namespace', { exact: false })).toHaveCount(0);
});

test('cds-arrow maps to an editable CDS and unknown predictions keep the draft', async ({ page }) => {
  let unknown = false;
  await page.route('**/api/inference/', route => route.fulfill({ json: {
    pred_classes: [unknown ? 'future-glyph' : 'cds-arrow'], draw_boxes: [[0, 0, 10, 10]], has_predictions: true, result_image: pixel,
  } }));
  await upload(page);
  const part = page.locator('.MuiAccordion-root').nth(1);
  await part.locator('.MuiAccordionSummary-root').click();
  await expect(part.getByRole('combobox', { name: 'Role', exact: true })).toHaveValue('CDS');
  await page.getByLabel('Namespace', { exact: false }).fill('https://example.org/keep');
  unknown = true;
  page.once('dialog', dialog => dialog.accept());
  await page.locator('#file-input').setInputFiles({ name: 'unknown.png', mimeType: 'image/png', buffer: Buffer.from(pixel, 'base64') });
  await expect(page.getByText(/Unknown detector class/)).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByLabel('Namespace', { exact: false })).toHaveValue('https://example.org/keep');
  await expect(part.getByRole('combobox', { name: 'Role', exact: true })).toHaveValue('CDS');
});

test('replacement import needs explicit discard confirmation', async ({ page }) => {
  await edit(page);
  page.once('dialog', dialog => dialog.dismiss());
  await page.locator('#file-input').setInputFiles({ name: 'replacement.png', mimeType: 'image/png', buffer: Buffer.from(pixel, 'base64') });
  await expect(page.locator('input[name=name]').first()).toHaveValue('Circuit');
  await expect(page.getByLabel('Namespace', { exact: false })).toHaveValue('https://example.org/research');
});

test('late camera permission after confirmed reset stops acquired tracks', async ({ page }) => {
  await page.addInitScript(() => {
    window.stoppedTracks = 0;
    navigator.mediaDevices.getUserMedia = () => new Promise(resolve => {
      window.resolveCamera = () => resolve({ getTracks: () => [{ stop: () => { window.stoppedTracks += 1; } }] });
    });
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Capture Image', exact: true }).click();
  await page.getByRole('button', { name: 'New design', exact: true }).click();
  await page.getByRole('button', { name: 'Discard and start new' }).click();
  await page.evaluate(() => window.resolveCamera());
  await expect.poll(() => page.evaluate(() => window.stoppedTracks)).toBe(1);
  await expect(page.getByText('Error accessing the camera.', { exact: true })).toHaveCount(0);
});


test('deleting an earlier operon cannot transfer union mode or erase manual edits', async ({ page }) => {
  await upload(page);
  const add = page.getByText('Operons', { exact: true }).locator('..').getByRole('button');
  await add.click();
  await add.click();
  const operon = name => page.getByText(name, { exact: true }).locator('xpath=ancestor::*[contains(@class,"MuiAccordion-root")][1]');
  const first = operon('Operon 1');
  const second = operon('Operon 2');
  await first.locator('.MuiAccordionSummary-root').click();
  await first.getByRole('checkbox', { name: 'Generate unions automatically by component order' }).check();
  await second.locator('.MuiAccordionSummary-root').click();
  await second.getByText('Unions', { exact: true }).locator('..').getByRole('button').click();
  await first.locator('[data-testid=DeleteIcon]').last().locator('..').click();
  await expect(operon('Operon 2').getByRole('checkbox', { name: 'Generate unions automatically by component order' })).not.toBeChecked();
  await expect(operon('Operon 2').getByRole('combobox', { name: 'From', exact: true })).toHaveCount(1);
});

test('generation requires review and editing or reordering invalidates that review', async ({ page }) => {
  await edit(page);
  const submit = page.getByRole('button', { name: 'Create SBOL 3 File' });
  const review = page.getByRole('checkbox', { name: /I have reviewed/ });
  await expect(submit).toBeDisabled();
  await review.check();
  await expect(submit).toBeEnabled();
  await page.locator('input[name=description]').first().fill('Updated design');
  await expect(review).not.toBeChecked();
  await review.check();
  await page.getByRole('button', { name: 'Move part right' }).first().click();
  await expect(review).not.toBeChecked();
  await expect(page.locator('input[name=name]').nth(1)).toHaveValue('RBSPart');
});
