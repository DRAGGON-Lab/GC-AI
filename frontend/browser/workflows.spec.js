/* eslint-env node */
import { test as base, expect } from '@playwright/test';
import JSZip from 'jszip';

const pixel = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jWZkAAAAASUVORK5CYII=';
const handle = 'v1_' + 'A'.repeat(43);
export const test = base.extend({
  page: async ({ page }, use) => {
    const unexpected = [];
    const errors = [];
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
