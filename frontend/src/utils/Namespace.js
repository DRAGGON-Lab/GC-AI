export const validateNamespace = (namespace) => {
  if (typeof namespace !== 'string' || !namespace || (/\s/.test(namespace) || [...namespace].some(c => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127))) {
    return 'Namespace is required and must not contain whitespace';
  }
  try {
    const url = new URL(namespace);
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname ||
        url.username || url.password || namespace.split('/')[2]?.includes('@') || namespace.includes('?') || namespace.includes('#') ||
        !/^https?:\/\/[^/]/i.test(namespace) || namespace.includes('\\')) {
      return 'Namespace must be an absolute HTTP(S) URL without credentials, query or fragment';
    }
  } catch {
    return 'Namespace must be a valid absolute HTTP(S) URL';
  }
  return null;
};
