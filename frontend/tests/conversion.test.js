import test from 'node:test';
import assert from 'node:assert/strict';
import JSZip from 'jszip';
import { conversionArtifacts } from '../src/utils/Conversion.js';

async function archive(files) {
  const zip = new JSZip();
  for (const [name, data] of Object.entries(files)) zip.file(name, data);
  return zip.generateAsync({ type: 'uint8array' });
}

test('conversion validates all requested downloads before returning any', async () => {
  const both = { genbank: true, fasta: true };
  const outputs = await conversionArtifacts(await archive({'design.gb':'LOCUS', 'design.fasta':'>seq\natgc'}), both);
  assert.equal(outputs.length, 2);
  for (const files of [{}, {'design.gb':'LOCUS'}, {'design.gb':'', 'design.fasta':'>seq'}, {'design.gb':'LOCUS', 'duplicate.gb':'LOCUS'}]) {
    await assert.rejects(conversionArtifacts(await archive(files), both), /archive/);
  }
});
