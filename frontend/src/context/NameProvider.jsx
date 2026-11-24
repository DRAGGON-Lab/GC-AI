/* eslint-disable react/prop-types */
import { useState, useEffect, useMemo, useRef } from 'react';
import NameContext from './NameContext';
import { Alert, Button } from '@mui/material';
import { loadNames } from '../utils/LoadNames.js';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

const NameProvider = ({ children }) => {
  const [namesCache, setNamesCache] = useState({});
  const [status, setStatus] = useState('loading');
  const [attempt, setAttempt] = useState(0);
  const successfulNames = useRef({});
  const roles = useMemo(() => [
    'Aptamer-RNA', 'Aptamer-DNA', 'Inert-DNA-Spacer', 'Ncrna', 'PolyA-Site',
    'Promoter', 'CDS', 'RBS', 'Operator',
    'Primer-Binding-Site', 'Origin-Of-Transfer', 'Origin-Of-Replication', 'Terminator', 'Engineered-Region',
  ], []);

  useEffect(() => {
    const controller = new AbortController();
    setStatus('loading');
    loadNames(roles, {
      baseUrl: API_BASE_URL,
      signal: controller.signal,
      existingNames: successfulNames.current,
    }).then(result => {
      if (controller.signal.aborted) return;
      successfulNames.current = result.namesCache;
      setNamesCache(result.namesCache);
      setStatus(result.failedRoles.length ? 'error' : 'ready');
    }).catch(() => {
      if (!controller.signal.aborted) setStatus('error');
    });
    return () => controller.abort();
  }, [roles, attempt]);

  return (
    <NameContext.Provider value={{ namesCache, roles }}>
      {status !== 'ready' && <Alert severity={status === 'loading' ? 'info' : 'warning'} action={
        <Button disabled={status === 'loading'} onClick={() => setAttempt(value => value + 1)}>Retry registry</Button>
      }>
        {status === 'loading' ? 'Loading registry parts. Manual entry is available.' :
          'Some registry parts could not be loaded. Retry or use Add Custom Component for manual entry.'}
      </Alert>}
      {children}
    </NameContext.Provider>
  );
};

export default NameProvider;
