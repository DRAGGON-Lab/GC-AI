import JSZip from 'jszip';

export async function conversionArtifacts(blob, formats) {
  const zip = await JSZip.loadAsync(blob);
  const files = Object.values(zip.files).filter(file => !file.dir);
  const expected = [formats.fasta && '.fasta', formats.genbank && '.gb'].filter(Boolean);
  if (!expected.length || files.length !== expected.length || expected.some(ext => files.filter(f => f.name.endsWith(ext)).length !== 1)) {
    throw new Error('The conversion archive is incomplete. Please retry.');
  }
  const downloads = await Promise.all(files.map(async file => ({ name: file.name, data: await file.async('uint8array') })));
  if (downloads.some(file => !file.data.length)) throw new Error('The conversion archive contains an empty file. Please retry.');
  return downloads;
}
