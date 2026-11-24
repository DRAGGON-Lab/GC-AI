/* eslint-disable react/prop-types */
import { useState, useEffect, useMemo, useRef } from 'react';
import NameContext from './NameContext';
import { Alert, Box, Button, Container, Paper } from '@mui/material';
import Navbar from '../components/Navbar/Navbar';
import LoadingScreen from '../components/LoadingScreen/LoadingScreen';
import Footer from '../components/Footer/Footer';
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

  if (status !== 'ready') {
    return (

      <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        <Navbar />
        <Container maxWidth="md" sx={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <Paper elevation={3} sx={{ p: 5, mt: 2, width: '100%', border: '3px solid #1b4a3b', borderRadius: 2, boxShadow: '1px 1px 15px 5px #1b4a3b', mb: 2, height: '100%' }}>
            {status === 'loading' ? <LoadingScreen message="data" /> : (
              <Alert severity="error" action={
                <Button color="inherit" onClick={() => setAttempt(value => value + 1)}>Retry</Button>
              }>
                We couldn’t load the available parts. Please try again.
              </Alert>
            )}
          </Paper>
        </Container>
        <Footer />
      </Box>

    );
  }

  return (
    <NameContext.Provider value={{ namesCache, roles }}>
      {children}
    </NameContext.Provider>
  );
};

export default NameProvider;
